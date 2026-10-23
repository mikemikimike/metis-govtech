---
title: Pre-requisites
---

Prepare your application and Langfuse before you run an evaluation.
You can build a specification before this setup is complete.

## Connect your application

<p className="draft-note">
  Draft. Write this section when the user simulation work defines the target binding.
</p>

## Connect Langfuse

Your application must send its traces to Langfuse. Group the traces of each trial
under the session ID that the runner returns. The Engine uses this ID to get the
conversation for grading.

Add the Langfuse credentials to `.env`:

```dotenv
LANGFUSE_PUBLIC_KEY=your-public-key
LANGFUSE_SECRET_KEY=your-secret-key
LANGFUSE_BASE_URL=https://your-langfuse-host
```

Make sure that a test conversation shows in Langfuse before you run the graders.

## Next step

[Build your specification](wizard.md).
