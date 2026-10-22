---
title: Installation
---

Install METIS and set up your model provider.

## 1. Install the tools

Install Python 3.11 or later and Git.

## 2. Install METIS

Create a virtual environment and install METIS from the GitHub repository:

```bash
python -m venv .venv
source .venv/bin/activate
pip install "git+https://github.com/govtech-responsibleai/metis@main"
```

<p className="code-caption">
  Draft. When <code>main</code> gets the beta tag, replace <code>@main</code> with that tag.
</p>

Check the installation:

```bash
metis --help
```

### Development install

To contribute to METIS, clone the repository and install it in development mode. You also need
[uv](https://docs.astral.sh/uv/getting-started/installation/), Node.js 22 or later, and Make:

```bash
git clone --branch next https://github.com/govtech-responsibleai/metis.git
cd metis
make install
uv run metis --help
```

## 3. Set up the `.env` file

Create a `.env` file in the folder where you run METIS.
Set the values for your model provider:

```dotenv
OPENAI_API_KEY=your-model-provider-key
OPENAI_BASE_URL=https://your-provider/v1
INTERVIEW_MODEL=your-interview-model
USER_AGENT_MODEL=your-simulation-model
JUDGE_MODEL=your-grading-model
```

In a clone, copy the example file to the repository root instead:

```bash
cp packages/wizard/.env.example .env
```

## 4. Install the browser tools (optional)

For browser simulation with Playwright, install Chromium and its dependencies.
In a clone, run:

```bash
make install-extras-playwright
```

## Next step

Prepare your application and Langfuse in [Pre-requisites](prerequisites.md).
