from __future__ import annotations

import html
import logging
import random
import re
import time
from bs4 import BeautifulSoup
from typing import Dict, List, Tuple, Optional

import requests
from requests import Response

from src.config import settings

logger = logging.getLogger(__name__)

def _strip_html(raw: str) -> str:
        return BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)



def _post_with_retries(
    url: str,
    headers: Dict[str, str],
    payload: Dict,
    *,
    max_retries: int = 5,
    base_backoff: float = 1.0,
) -> Response:
    for attempt in range(max_retries + 1):
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp

        if attempt == max_retries:
            resp.raise_for_status()
        sleep = base_backoff * (2**attempt) + random.random()
        logger.warning("Vertex 429 – retry %s in %.2fs", attempt + 1, sleep)
        time.sleep(sleep)
        return None
    return None




def _build_generation_prompt(name: str, features: str, langs: List[str]) -> str:
    lang_list = ", ".join(langs)
    return (
        "You are an expert e-commerce copywriter. For each language listed, "
        "return a block starting with `=== [LANG]` followed by an <h3> title "
        "and a short HTML description (max 240 words).\n\n"
        f"Languages: {lang_list}\n\n"
        f"Product name: {name}\nFeatures: {features}"
    )


def _build_translation_prompt(name: str, html_desc: str, target: List[str]) -> str:
    langs = ", ".join(target)
    return (
        f"Translate the following product name and HTML description into: {langs}. "
        f"Keep HTML tags intact. Each block must start with `=== [LANG]`.\n\n"
        f"Product name: {name}\nDescription: {html_desc}"
    )


def _parse_vertex_output(text: str) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    parts = re.split(r"===\s*([A-Za-z]{2})\s*", text)
    it = iter(parts[1:])  # skip first empty
    for lang, block in zip(it, it):
        block = block.strip()
        h3 = re.search(r"<h3>(.*?)</h3>", block, re.I)
        name = html.unescape(h3.group(1).split(":")[0].strip()) if h3 else ""
        out[lang.lower()] = {"product_name": name, "description": block}
    return out

def generate_multilingual_descriptions(
    *,
    product_id: str,
    name: str,
    features: str,
    input_language: str,
    target_languages: List[str],
    description_html: str | None = None,
    return_error: bool = False,
) -> Dict[str, Dict[str, str]] | Tuple[Dict[str, Dict[str, str]], Optional[str]]:
    if not settings.VERTEX_API_KEY or not settings.VERTEX_MODEL_ID:
        err = "missing_creds"
        logger.error("Vertex creds missing")
        return ({}, err) if return_error else {}

    languages = [input_language] + [l for l in target_languages if l != input_language]

    if description_html:
        prompt = _build_translation_prompt(name, description_html, target_languages)
    else:
        prompt = _build_generation_prompt(name, _strip_html(features), languages)

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.VERTEX_MODEL_ID}:generateContent?key={settings.VERTEX_API_KEY}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        resp = _post_with_retries(url, {"Content-Type": "application/json"}, payload)
        data = resp.json()
        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text")
        ) or ""

        if not text.strip():
            err = "empty_response"
            logger.error("Vertex empty response pid=%s | raw=%s", product_id, data)
            return ({}, err) if return_error else {}

        result = _parse_vertex_output(text)
        return (result, None) if return_error else result

    except Exception as exc:
        err = str(exc)
        logger.error("Vertex exception pid=%s → %s", product_id, err)
        return ({}, err) if return_error else {}