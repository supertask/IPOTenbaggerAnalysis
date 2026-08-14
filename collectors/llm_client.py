"""AIに文章を書かせるところを1箇所にまとめる。

**開示の要約だけでなく、これから足す処理でも使う。** 呼ぶ側は
`ask(prompt)` を呼ぶだけで、どのモデルにどう投げるかはここで決まる。

## 使い分け

| バックエンド | 何 | 上限 |
|---|---|---|
| `openrouter` | OpenRouterの無料モデル（既定） | **1日1,000リクエスト**（累計$10購入済み）／1分20 |
| `lmstudio` | 別PCのLM Studio（Tailscale経由） | 上限なし。電気代だけ |

    python collectors/disclosure_ai_summary.py --backend lmstudio

    from collectors.llm_client import LLM
    llm = LLM.from_name("lmstudio")
    text, usage = llm.ask("…")

## 設定は環境変数から

**URLもキーもリポジトリに書かない**（ここは公開リポジトリ）。
設定が無いバックエンドは、呼んだ時点で理由を添えて落ちる。

| 環境変数 | 何に使うか |
|---|---|
| `OPENROUTER_API_KEY_PERSONAL` | OpenRouterのキー |
| `OPENROUTER_MODEL` | 使うモデル（既定は Nemotron 3 Ultra の無料版） |
| `LMSTUDIO_BASE_URL` | 例 `http://100.x.x.x:1234/v1`。**Tailscaleのアドレスは書かない** |
| `LMSTUDIO_MODEL` | LM Studioに読み込ませているモデルID |
| `LLM_BACKEND` | 既定のバックエンド。`--backend` を省いたときに使う |

LM Studio側は「Serve on Local Network」を有効にしておくこと。
既定では127.0.0.1でしか待たないので、別のPCからは繋がらない。
"""
from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import requests

# 推論するモデルは考える過程を長く吐く。実測で reasoning だけ4,800トークン出た。
# ここが小さいとJSONを吐き切る前に打ち切られて、1件も返らない
DEFAULT_MAX_TOKENS = 12000


@dataclass
class Backend:
    name: str
    base_url: str
    model: str
    api_key: str
    # 同時にいくつ投げられるか。OpenRouterは1分20リクエストの上限があるので
    # 8本まで。ローカルは並列スロットの数しだいで、まず4本から試す
    workers: int
    timeout: int = 300


def _openrouter() -> Backend:
    key = os.environ.get("OPENROUTER_API_KEY_PERSONAL", "").strip()
    if not key:
        raise SystemExit(
            "環境変数 OPENROUTER_API_KEY_PERSONAL が要ります。"
            "公開リポジトリなのでキーはコードに書きません")
    return Backend(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        model=os.environ.get("OPENROUTER_MODEL",
                             "nvidia/nemotron-3-ultra-550b-a55b:free"),
        api_key=key,
        workers=int(os.environ.get("OPENROUTER_WORKERS", "8")),
    )


def _lmstudio() -> Backend:
    base = os.environ.get("LMSTUDIO_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise SystemExit(
            "環境変数 LMSTUDIO_BASE_URL が要ります（例 http://100.x.x.x:1234/v1）。"
            "Tailscaleのアドレスはリポジトリに書かないので環境変数から取ります")
    return Backend(
        name="lmstudio",
        base_url=base,
        model=os.environ.get("LMSTUDIO_MODEL", "qwen3.6-35b-a3b"),
        api_key=os.environ.get("LMSTUDIO_API_KEY", "lm-studio"),
        workers=int(os.environ.get("LMSTUDIO_WORKERS", "4")),
        timeout=900,   # ローカルは1件が長い。待てる時間を長めに取る
    )


BACKENDS = {"openrouter": _openrouter, "lmstudio": _lmstudio}


class LLM:
    """OpenAI互換のチャットAPIに投げる。どちらのバックエンドも同じ形"""

    def __init__(self, backend: Backend):
        self.backend = backend

    @classmethod
    def from_name(cls, name: Optional[str] = None) -> "LLM":
        name = (name or os.environ.get("LLM_BACKEND") or "openrouter").strip()
        if name not in BACKENDS:
            raise SystemExit(f"--backend は {sorted(BACKENDS)} のどれか（指定: {name}）")
        return cls(BACKENDS[name]())

    def ask(self, prompt: str, tries: int = 4,
            max_tokens: int = DEFAULT_MAX_TOKENS,
            temperature: float = 0.2) -> Tuple[Optional[str], dict]:
        """返答の本文と usage。**必ずリトライする** —
        無料枠は502や429が普通に出るし、ローカルもモデルの入れ替え中は落ちる"""
        b = self.backend
        delay = 3.0
        last = ""
        for attempt in range(tries):
            try:
                res = requests.post(
                    f"{b.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {b.api_key}"},
                    json={"model": b.model,
                          "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": max_tokens,
                          "temperature": temperature},
                    timeout=b.timeout)
                data = res.json()
            except Exception as exc:
                last = f"通信エラー {type(exc).__name__} {exc}"[:160]
            else:
                if "error" in data:
                    last = json.dumps(data["error"], ensure_ascii=False)[:160]
                elif not data.get("choices"):
                    last = json.dumps(data, ensure_ascii=False)[:160]
                else:
                    return (data["choices"][0]["message"]["content"],
                            data.get("usage") or {})
            if attempt < tries - 1:
                time.sleep(delay + random.uniform(0, 1.5))
                delay *= 2
        return None, {"error": last}

    def check(self) -> str:
        """疎通の確認。使えれば説明、駄目なら理由を返す"""
        text, usage = self.ask("「疎通OK」とだけ返して", tries=1, max_tokens=2000)
        b = self.backend
        if text is None:
            return f"{b.name} に繋がりません（{b.base_url} / {b.model}）: {usage.get('error')}"
        return (f"{b.name} OK（{b.model} / 同時{b.workers}本）"
                f" 返答 {text.strip()[:20]!r}")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="バックエンドの疎通を確認する")
    parser.add_argument("--backend", choices=sorted(BACKENDS))
    args = parser.parse_args()
    names = [args.backend] if args.backend else sorted(BACKENDS)
    for name in names:
        try:
            print(LLM.from_name(name).check())
        except SystemExit as exc:
            print(f"{name}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
