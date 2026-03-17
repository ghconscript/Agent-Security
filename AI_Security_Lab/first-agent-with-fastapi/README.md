# First Agent

A FastAPI-based chat server powered by LangChain agents with custom tools.

## Overview

This project implements a simple chat API that uses a LangChain agent with GPT-4o. The agent has access to custom tools, including a weather lookup function.

## Features

- FastAPI REST API with `/chat` endpoint
- LangChain agent integration with GPT-4o
- Custom tool: `get_weather` function
- Environment variable configuration
- Poetry for dependency management

## Prerequisites

- Python ^3.12
- Poetry (for dependency management)
- OpenAI API key

## Installation

1. Clone the repository and navigate to the project directory

2. Install dependencies using Poetry:
```bash
poetry install
```

3. Create a `.env` file in the project root:
```env
OPENAI_API_KEY=your_api_key_here
PORT=8000
```

## Usage

### Running the Server

```bash
poetry run python server.py
```

The server will start on `http://0.0.0.0:8000` (or the port specified in your `.env` file).

### API Endpoint

**POST** `/chat`

Request body:
```json
{
  "message": "what is the weather in san francisco"
}
```

Response:
```json
{
  "reply": "It's always sunny in san francisco!"
}
```

### Example with curl

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "what is the weather in san francisco"}'
```

## Project Structure

```
first-agent/
├── server.py          # Main FastAPI application
├── pyproject.toml     # Poetry dependencies
├── .env              # Environment variables (not in repo)
└── README.md         # This file
```

## Dependencies

- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `langchain` - Agent framework
- `langchain-openai` - OpenAI integration
- `python-dotenv` - Environment variable management

## Configuration

The following environment variables can be configured:

- `OPENAI_API_KEY` - Your OpenAI API key (required)
- `PORT` - Server port (default: 8000)

## License

No license specified.

## Author

Manish Shivanandhan <manish@manalath.com>
