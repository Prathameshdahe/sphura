"""Export sphura-fin-1.7b: merge the LoRA into fp16 safetensors → GGUF → Ollama → smoke test.

    training/.venv/Scripts/python training/sft/export.py --run sphura-fin-1.7b [--tag sphura-fin-1.7b]

Steps: (1) merge adapter + Qwen/Qwen3-1.7B → training/runs/<run>/merged (fp16 safetensors + tokenizer);
(2) llama.cpp's convert_hf_to_gguf.py --outtype q8_0 → training/runs/<run>/<run>-q8_0.gguf; (3) a Modelfile (FROM the
GGUF; Qwen3 non-thinking TEMPLATE, tool calling only with --tools; PARAMETERs; the training SYSTEM prompt) and `ollama create <tag>`;
(4) ten finance prompts plus one tool-calling prompt through the Ollama API → backend/ml/artifacts/finetune/smoke.json;
(5) `ollama stop` everything it loaded.

Why not `ollama create --quantize q4_K_M` (the plan's first choice): the dry run on a tiny Qwen3 showed that Ollama
0.40.3 only quantizes *safetensors* imports, and only to int4 / int8 / nvfp4 / mxfp4 / mxfp8, and refuses create-time
quantization of a GGUF ("quantize GGUF models before importing"). K-quants would need a compiled llama-quantize, so
the default is llama.cpp's pure-Python Q8_0 (≈1.8 GB, near-lossless). `--via safetensors --quantize int4` tries
Ollama's own safetensors import instead (falls back to the GGUF path if it fails).
Takes the GPU lock while merging (GPU merge); `--cpu` merges on the CPU without the lock (dry run on a tiny model).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from contextlib import nullcontext
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRAINING_DIR = HERE.parent
REPO = TRAINING_DIR.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TRAINING_DIR))

from gpu_lock import gpu_lock, is_busy, stop_ollama_models  # noqa: E402
from ollama_client import ollama_chat  # noqa: E402
from prompts import SYSTEM_PROMPT  # noqa: E402

BASE = "Qwen/Qwen3-1.7B"
ARTIFACT_DIR = REPO / "backend" / "ml" / "artifacts" / "finetune"
SMOKE_PROMPTS = [
    "What is a SIP?", "EMI on 10 lakh at 9% for 5 years", "I earn 12 LPA, which tax regime is better?",
    "How does 80C work?", "What are the GST slabs?", "What happens if a UPI payment fails but money is debited?",
    "Is 750 a good credit score?", "What is the current ratio and what does it mean?", "Should I buy Reliance?",
    "Write a Python script to sort a list",
]
EMI_TOOL = {"type": "function", "function": {
    "name": "emi", "description": "Monthly EMI for a loan (reducing balance).",
    "parameters": {"type": "object", "required": ["principal", "annual_rate", "years"], "properties": {
        "principal": {"type": "number", "description": "loan amount in rupees"},
        "annual_rate": {"type": "number", "description": "annual interest rate in percent"},
        "years": {"type": "number", "description": "tenure in years"}}}}}
# Qwen3 chat format with thinking disabled (the empty <think></think> block the HF template adds when
# enable_thinking=False, exactly as in training). TEMPLATE_TOOLS adds Qwen3's <tools>/<tool_call> convention; it is
# opt-in (--tools) because the tuned model was trained without tool rows. Caveat measured on Ollama 0.40.3: Ollama
# also reads the Jinja chat template that convert_hf_to_gguf embeds in the GGUF and advertises `tools` + `thinking`
# from it whatever TEMPLATE says, and with tools bound the tuned model emits its call as bare JSON without the
# <tool_call> wrapper (2 of 4 probes), which Ollama does not parse. Callers should not bind tools to this model.
TEMPLATE_PLAIN = '''{{- if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}
{{- range $i, $_ := .Messages }}
{{- $last := eq (len (slice $.Messages $i)) 1 -}}
{{- if eq .Role "user" }}<|im_start|>user
{{ .Content }}<|im_end|>
{{ else if eq .Role "assistant" }}<|im_start|>assistant
{{ .Content }}{{ if not $last }}<|im_end|>
{{ end }}
{{- else if eq .Role "tool" }}<|im_start|>user
<tool_response>
{{ .Content }}
</tool_response><|im_end|>
{{ end }}
{{- if and (ne .Role "assistant") $last }}<|im_start|>assistant
<think>

</think>

{{ end }}
{{- end }}'''
TEMPLATE_TOOLS = '''{{- if or .System .Tools }}<|im_start|>system
{{- if .System }}
{{ .System }}
{{- end }}
{{- if .Tools }}

# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
{{- range .Tools }}
{"type": "function", "function": {{ .Function }}}
{{- end }}
</tools>

For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
<tool_call>
{"name": <function-name>, "arguments": <args-json-object>}
</tool_call>
{{- end }}<|im_end|>
{{ end }}
{{- range $i, $_ := .Messages }}
{{- $last := eq (len (slice $.Messages $i)) 1 -}}
{{- if eq .Role "user" }}<|im_start|>user
{{ .Content }}<|im_end|>
{{ else if eq .Role "assistant" }}<|im_start|>assistant
{{ if .Content }}{{ .Content }}
{{- else if .ToolCalls }}<tool_call>
{{ range .ToolCalls }}{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}
{{ end }}</tool_call>
{{- end }}{{ if not $last }}<|im_end|>
{{ end }}
{{- else if eq .Role "tool" }}<|im_start|>user
<tool_response>
{{ .Content }}
</tool_response><|im_end|>
{{ end }}
{{- if and (ne .Role "assistant") $last }}<|im_start|>assistant
<think>

</think>

{{ end }}
{{- end }}'''


def merge(run_dir: Path, base_id: str, device: str) -> Path:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    merged = run_dir / "merged"
    if (merged / "config.json").exists() and any(merged.glob("*.safetensors")):
        print(f"[merge] reusing {merged}")
        return merged
    adapter = run_dir / "adapter"
    print(f"[merge] loading {base_id} in fp16 on {device}")
    base = AutoModelForCausalLM.from_pretrained(base_id, dtype=torch.float16,
                                                device_map={"": 0} if device == "cuda" else None)
    model = PeftModel.from_pretrained(base, str(adapter))
    model = model.merge_and_unload()
    merged.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(merged), safe_serialization=True, max_shard_size="2GB")
    AutoTokenizer.from_pretrained(str(adapter)).save_pretrained(str(merged))
    print(f"[merge] saved {merged}")
    del model, base
    if device == "cuda":
        torch.cuda.empty_cache()
    return merged


def write_modelfile(run_dir: Path, source: Path, tools: bool = False) -> Path:
    path = run_dir / "Modelfile"
    system = SYSTEM_PROMPT.replace('"""', "'''")
    template = TEMPLATE_TOOLS if tools else TEMPLATE_PLAIN
    path.write_text(
        f"FROM {source.resolve().as_posix()}\n"
        f'TEMPLATE """{template}"""\n'
        f'SYSTEM """{system}"""\n'
        "PARAMETER stop <|im_end|>\nPARAMETER stop <|im_start|>\nPARAMETER stop <|endoftext|>\n"
        "PARAMETER temperature 0.7\nPARAMETER top_p 0.8\nPARAMETER top_k 20\nPARAMETER repeat_penalty 1.05\n"
        "PARAMETER num_ctx 4096\n"
        'LICENSE """Qwen3-1.7B: Apache-2.0 (Alibaba Cloud). Fine-tune data: see backend/ml/data/README.md."""\n',
        encoding="utf-8")
    return path


def ollama_create(tag: str, modelfile: Path, quantize: str) -> tuple[bool, str]:
    cmd = ["ollama", "create", tag, "-f", str(modelfile)] + (["--quantize", quantize] if quantize else [])
    print("[ollama]", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=str(modelfile.parent))
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out[-2000:])
    return proc.returncode == 0, out


def convert_with_llama_cpp(merged: Path, run_dir: Path, outtype: str) -> Path:
    """llama.cpp's converter → GGUF (f16 / bf16 / q8_0). Uses llama.cpp's own gguf-py; reuses an existing file."""
    llama = TRAINING_DIR / "llama.cpp"
    if not (llama / "convert_hf_to_gguf.py").exists():
        subprocess.run(["git", "clone", "--depth", "1", "https://github.com/ggml-org/llama.cpp", str(llama)], check=True)
    gguf = run_dir / f"{run_dir.name}-{outtype}.gguf"
    if gguf.exists() and gguf.stat().st_mtime > (merged / "config.json").stat().st_mtime:
        print(f"[gguf] reusing {gguf}")
        return gguf
    subprocess.run([sys.executable, str(llama / "convert_hf_to_gguf.py"), str(merged), "--outtype", outtype, "--outfile",
                    str(gguf)], check=True, env={**os.environ, "PYTHONPATH": str(llama / "gguf-py")})
    return gguf


def smoke_test(tag: str) -> list[dict]:
    results = []
    for prompt in SMOKE_PROMPTS:
        started = time.perf_counter()
        try:
            data = ollama_chat(tag, [{"role": "user", "content": prompt}], num_predict=220, temperature=0.7)
            text = data["message"]["content"].strip()
            eval_count = data.get("eval_count")
            eval_s = (data.get("eval_duration") or 0) / 1e9
            results.append({"prompt": prompt, "answer": text, "seconds": round(time.perf_counter() - started, 2),
                            "tokensPerSecond": round(eval_count / eval_s, 1) if eval_count and eval_s else None})
            print(f"[smoke] {prompt!r} ({results[-1]['seconds']}s, {results[-1]['tokensPerSecond']} tok/s)\n  "
                  f"{text[:220].replace(chr(10), ' ')}")
        except Exception as exc:  # noqa: BLE001
            results.append({"prompt": prompt, "error": f"{type(exc).__name__}: {exc}"})
            print(f"[smoke] {prompt!r} failed: {exc}")
    return results


def tool_smoke(tag: str) -> dict:
    """One prompt with an `emi` tool bound: does the model emit a structured tool call through Ollama?"""
    from ollama_client import OLLAMA_URL, post_json

    prompt = "EMI for a 25 lakh home loan at 8.5% for 20 years?"
    body = {"model": tag, "stream": False, "think": False, "tools": [EMI_TOOL],
            "messages": [{"role": "user", "content": prompt}], "options": {"temperature": 0, "num_predict": 160}}
    try:
        msg = post_json(f"{OLLAMA_URL}/api/chat", body)["message"]
    except Exception as exc:  # noqa: BLE001
        return {"prompt": prompt, "toolCalls": None, "error": f"{type(exc).__name__}: {exc}"}
    calls = [c.get("function") for c in msg.get("tool_calls") or []]
    print(f"[smoke] tool call: {calls or msg.get('content', '')[:160]!r}")
    return {"prompt": prompt, "toolCalls": calls, "content": (msg.get("content") or "")[:400]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="sphura-fin-1.7b")
    ap.add_argument("--tag", default="sphura-fin-1.7b")
    ap.add_argument("--via", choices=("gguf", "safetensors"), default="gguf")
    ap.add_argument("--gguf-type", choices=("q8_0", "f16", "bf16"), default="q8_0")
    ap.add_argument("--quantize", default="int4", help="Ollama create-time quantization (safetensors path only)")
    ap.add_argument("--base", default=BASE, help="base model id/dir the adapter was trained on")
    ap.add_argument("--runs-dir", type=Path, default=TRAINING_DIR / "runs")
    ap.add_argument("--artifact-dir", type=Path, default=ARTIFACT_DIR)
    ap.add_argument("--cpu", action="store_true", help="merge on the CPU without taking the GPU lock")
    ap.add_argument("--skip-smoke", action="store_true")
    ap.add_argument("--tools", action="store_true", help="tool-calling TEMPLATE (see the TEMPLATE_PLAIN comment)")
    args = ap.parse_args()
    run_dir = args.runs_dir / args.run
    assert (run_dir / "adapter").exists(), f"no adapter in {run_dir}"

    import torch

    device = "cpu" if args.cpu or not torch.cuda.is_available() else "cuda"
    with nullcontext() if device == "cpu" else gpu_lock(f"export-{args.run}"):
        merged = merge(run_dir, args.base, device)
    ok, log, method, quant = False, "", "", ""
    if args.via == "safetensors":
        modelfile = write_modelfile(run_dir, merged, args.tools)
        ok, log = ollama_create(args.tag, modelfile, args.quantize)
        method, quant = "ollama create from merged safetensors", args.quantize
        if not ok:
            print("[ollama] safetensors import failed; converting with llama.cpp")
    if not ok:
        gguf = convert_with_llama_cpp(merged, run_dir, args.gguf_type)
        modelfile = write_modelfile(run_dir, gguf, args.tools)
        ok, log = ollama_create(args.tag, modelfile, "")
        method, quant = f"llama.cpp convert_hf_to_gguf --outtype {args.gguf_type} → ollama create", args.gguf_type
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    info = {"tag": args.tag if ok else None, "method": method, "quantize": quant, "created": ok, "toolTemplate": args.tools,
            "modelfile": modelfile.resolve().relative_to(REPO).as_posix() if modelfile.resolve().is_relative_to(REPO)
            else str(modelfile), "log": log[-1500:],
            "exportedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if ok and not args.skip_smoke and is_busy():
        info["smokeSkipped"] = "training/GPU_BUSY exists: another GPU job is running, Ollama not called"
    elif ok and not args.skip_smoke:
        stop_ollama_models()
        info["smoke"] = smoke_test(args.tag)
        info["toolSmoke"] = tool_smoke(args.tag)
        stop_ollama_models()
    (args.artifact_dir / "smoke.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    # the published copy points next to itself, not at this machine's run folder
    lines = modelfile.read_text(encoding="utf-8").splitlines(keepends=True)
    lines[0] = f"FROM ./{Path(lines[0][5:].strip()).name}\n"
    (args.artifact_dir / "Modelfile").write_text("".join(lines), encoding="utf-8")
    print(f"[export] {'created' if ok else 'FAILED'} {args.tag}; details in {args.artifact_dir / 'smoke.json'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
