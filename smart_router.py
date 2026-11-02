"""
title: Smart Router
author: dinesh
version: 1.6
description: Routes to Quick Chat, Deep Reasoning or Smart Assistant. Unclear questions are classified by a small model. Live questions read the top search pages. Date and time come from the server clock.
"""

import asyncio
import inspect
import logging
import re
from datetime import datetime
from fastapi import Request
from pydantic import BaseModel, Field

from open_webui.models.users import Users
from open_webui.utils.chat import generate_chat_completion

log = logging.getLogger("smart_router")

DISPLAY_NAMES = {
    "fast-chat": "⚡Quick Chat",
    "reasoning": "🧠Deep Reasoning",
    "smart-assistant": "🤖Smart Assistant",
}

TIME_WORDS = "date,din,tarikh,taareekh,time,samay,baje,kya time,aaj ki date,aaj kya hai"
WEATHER_WORDS = "weather,mausam,temperature,barish,rain,garmi,thand,humidity"
CITY_RE = re.compile(r"([a-z]+)\s+(?:ka|ki|ke)\s+(?:weather|mausam|temperature)")
CITY_STOP = {
    "aaj",
    "kal",
    "abhi",
    "ab",
    "aj",
    "today",
    "tomorrow",
    "kaun",
    "sa",
    "ka",
    "ki",
}
CATEGORIES = {"live", "code", "math", "general", "chat"}


def _fetch_page(url, limit=1500):
    try:
        import httpx

        r = httpx.get(
            url,
            timeout=6,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", r.text)
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()[:limit]
    except Exception as e:
        log.warning("page fetch failed %s: %s", url, e)
        return ""


class Pipe:
    class Valves(BaseModel):
        ID_FAST: str = Field(default="fast-chat")
        ID_REASON: str = Field(default="reasoning")
        ID_SMART: str = Field(default="smart-assistant")
        LONG_PROMPT_CHARS: int = Field(default=400)
        SEARCH_RESULTS: int = Field(default=5)
        PAGE_READS: int = Field(default=2)
        DEFAULT_CITY: str = Field(default="Pune")
        LIVE_WORDS: str = Field(
            default="aaj,aaj ka,aaj ki,abhi,abhi ka,ab,date,din,tarikh,taareekh,time,samay,baje,kitne baje,kya time,ghanta,weather,mausam,temperature,barish,rain,garmi,thand,sensex,nifty,share,stock,price,rate,bhav,dollar,gold,petrol,news,khabar,latest,live,today,tomorrow,kal,current,score,kab,now,election"
        )
        CODE_WORDS: str = Field(
            default="code,python,function,bug,error,script,sql,streamlit,pandas,html,css,javascript,regex,debug,list,sort"
        )
        REASON_WORDS: str = Field(
            default="solve,calculate,kitna hota,math,logic,puzzle,prove,step by step,probability,equation"
        )
        GENERAL_WORDS: str = Field(
            default="analyze,analysis,explain,compare,why,plan,strategy,summarize,write,essay,insight,samjhao,batao,kya hota,kya hoti,matlab"
        )
        SHOW_ROUTE: bool = Field(default=True)

    def __init__(self):
        self.valves = self.Valves()

    def pipes(self):
        return [{"id": "smart-router", "name": "Smart Router"}]

    def _user_messages(self, body):
        return [
            (
                lambda c: (
                    " ".join(p.get("text", "") for p in c if isinstance(p, dict))
                    if isinstance(c, list)
                    else (c or "")
                )
            )(m.get("content", ""))
            for m in body.get("messages", [])
            if m.get("role") == "user"
        ]

    def _has_media(self, body):
        for m in body.get("messages", []):
            c = m.get("content")
            if isinstance(c, list):
                for p in c:
                    if isinstance(p, dict) and p.get("type") in (
                        "image_url",
                        "image",
                        "file",
                    ):
                        return True
        if body.get("files") or (body.get("metadata") or {}).get("files"):
            return True
        return False

    def _has(self, text, words_csv):
        for w in [x.strip().lower() for x in words_csv.split(",") if x.strip()]:
            if re.search(r"(?<!\w)" + re.escape(w), text):
                return True
        return False

    def _keyword_route(self, text):
        v = self.valves
        t = text.lower()
        if self._has(t, v.LIVE_WORDS + ",kaun,who"):
            return "live"
        if "```" in text or self._has(t, v.CODE_WORDS):
            return "code"
        if self._has(t, v.REASON_WORDS) or re.search(
            r"\d\s*[\+\*/\^×]\s*\d|\d\s+-\s+\d", t
        ):
            return "math"
        words = t.split()
        if len(words) <= 3 and len(text) <= 25 and not self._has(t, v.GENERAL_WORDS):
            return "chat"
        if self._has(t, v.GENERAL_WORDS) or len(text) > v.LONG_PROMPT_CHARS:
            return "general"
        return None

    async def _classify(self, text, request, user):
        body = {
            "model": self.valves.ID_FAST,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Classify the user's message into exactly one word: "
                        "live (needs current news, weather, prices, scores or today's facts), "
                        "code (programming), math (calculation or logic), "
                        "general (explanation, advice, writing), chat (greeting or small talk). "
                        "Reply with only that one word."
                    ),
                },
                {"role": "user", "content": text[:500]},
            ],
        }
        try:
            res = await asyncio.wait_for(
                generate_chat_completion(request, body, user), timeout=20
            )
            if inspect.isawaitable(res):
                res = await res
            content = res["choices"][0]["message"]["content"]
            for w in re.findall(r"[a-z]+", content.lower()):
                if w in CATEGORIES:
                    return w
        except Exception as e:
            log.warning("classifier failed: %s", e)
        return None

    def _search_query(self, text, prev):
        t = text.lower()
        if self._has(t, WEATHER_WORDS):
            m = CITY_RE.search(t)
            city = self.valves.DEFAULT_CITY
            if m and m.group(1) not in CITY_STOP:
                city = m.group(1).title()
            today = datetime.now().strftime("%d %B %Y")
            return f"{city} weather today {today} temperature humidity rain"
        q = text
        if prev and len(text.split()) <= 4:
            q = f"{prev} {text}"
        return q + " today"

    def _search_sync(self, query, n):
        try:
            from ddgs import DDGS

            with DDGS() as d:
                return list(d.text(query, max_results=n, region="in-en"))
        except Exception as e:
            log.warning("search failed: %s", e)
            return []

    async def _live_prompt(self, text, prev):
        query = self._search_query(text, prev)
        hits = await asyncio.to_thread(
            self._search_sync, query, self.valves.SEARCH_RESULTS
        )
        if hits:
            snippets = "\n".join(
                f"- {h.get('title', '')}: {h.get('body', '')} ({h.get('href', '')})"
                for h in hits
            )
        else:
            snippets = "No search results found."

        pages = []
        for h in hits[: self.valves.PAGE_READS]:
            url = h.get("href", "")
            if url:
                page = await asyncio.to_thread(_fetch_page, url)
                if page:
                    pages.append(f"Source: {url}\n{page}")
        page_text = "\n\n".join(pages) if pages else "No page text could be read."

        now = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
        return (
            f"Current server date and time: {now}\n\n"
            f"Search results:\n{snippets}\n\n"
            f"Text from the top pages:\n{page_text}\n\n"
            f"User question: {text}\n\n"
            "Answer using the material above. Give the actual numbers (temperature, humidity, "
            "rain chance, prices, scores) if they appear there, and name the source site. "
            "Do not just list links. If the material does not contain the answer, say so clearly "
            "and suggest the best link once. Never invent numbers, prices, scores or dates. "
            "Reply in the same language or script the user used (Roman Hinglish stays in Roman letters)."
        )

    async def pipe(
        self, body: dict, __user__: dict, __request__: Request, __event_emitter__=None
    ):
        users = self._user_messages(body)
        text = users[-1] if users else ""
        prev = users[-2] if len(users) >= 2 else ""
        t = text.lower()
        has_media = self._has_media(body)

        if (
            not has_media
            and self._has(t, TIME_WORDS)
            and not self._has(t, WEATHER_WORDS)
        ):
            now = datetime.now()
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {
                            "description": DISPLAY_NAMES["fast-chat"],
                            "done": True,
                        },
                    }
                )
            return (
                f"Aaj ki date: {now.strftime('%A, %d %B %Y')}\n"
                f"Abhi ka time: {now.strftime('%I:%M %p')} (server clock)"
            )

        user = Users.get_user_by_id(__user__["id"])
        if inspect.isawaitable(user):
            user = await user

        category = None
        if has_media:
            category = "general"
        else:
            category = self._keyword_route(text)
            if category is None:
                category = await self._classify(text, __request__, user) or "general"

        v = self.valves
        if category == "live":
            model_id, live = v.ID_SMART, True
        elif category == "math":
            model_id, live = v.ID_REASON, False
        elif category == "chat":
            model_id, live = v.ID_FAST, False
        else:
            model_id, live = v.ID_SMART, False

        log.info("route: '%s' -> %s category=%s", text[:60], model_id, category)

        if v.SHOW_ROUTE and __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": DISPLAY_NAMES.get(model_id, model_id),
                        "done": True,
                    },
                }
            )

        if live:
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {"description": "Searching the web...", "done": False},
                    }
                )
            try:
                prompt = await self._live_prompt(text, prev)
                for m in reversed(body.get("messages", [])):
                    if m.get("role") == "user":
                        m["content"] = prompt
                        break
            except Exception as e:
                log.warning("live prompt failed: %s", e)
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {"description": "Searching the web...", "done": True},
                    }
                )

        if model_id != v.ID_SMART:
            body.pop("tools", None)
            body.pop("tool_choice", None)

        for attempt in (model_id, v.ID_FAST):
            body["model"] = attempt
            try:
                return await generate_chat_completion(__request__, body, user)
            except Exception as e:
                log.warning("model '%s' failed: %s", attempt, e)

        return "I'm having trouble answering right now. Please try again in a little while."
