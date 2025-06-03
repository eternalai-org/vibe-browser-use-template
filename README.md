# Vibe XBrowser Templaate

## What can be customized?

### Toolcalls 

See: `app/toolcalls.py`

## Debugging

Prepare:
- Docker
- Some variables:

```bash
LLM_MODEL_ID=gpt-4o # just an example, use whatever you want or randomize if using local llm
LLM_BASE_URL=http://localhost:65534/v1 # or https://api.openai.com/v1
LLM_API_KEY=free # no need if using local llm but openai, yes
```

*(I commited a file named `.env.example`, all variables in this file should be pre-filled)*

Build the image 

```bash
docker build -t an_awesome_container_name . 
```

Run it

```bash
docker run --env-file .env.example -p 6080:6080 -p 8000:80 an_awesome_container_name 
```

In your browser, to to [This URL](http://localhost:6080/vnc.html?host=localhost&port=6080) to see what happen while the agent running.

Call the agent:

```bash
curl http://localhost:8000/prompt -d '
{
    "messages": [
        {
            "role": "user",
            "content": "yo"
        },
        {
            "role": "assistant",
            "content": "yo"
        },
        {
            "role": "user",
            "content": "to to amazon and buy all shoes"
        }
    ]
}
' # not tested yet
```