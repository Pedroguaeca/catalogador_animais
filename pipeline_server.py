"""
Servidor leve que encapsula main.py como endpoint SSE.
Usado em produção Docker; em dev local o Next.js chama conda run diretamente.
"""
import asyncio
import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/run")
async def run_pipeline():
    async def stream():
        proc = await asyncio.create_subprocess_exec(
            "python", "main.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            if line:
                yield f"data: {json.dumps(line)}\n\n"
        await proc.wait()
        code = proc.returncode
        if code == 0:
            yield f"data: {json.dumps('✅ Pipeline concluído com sucesso!')}\n\n"
        else:
            yield f"data: {json.dumps(f'❌ Pipeline encerrado com código {code}')}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
