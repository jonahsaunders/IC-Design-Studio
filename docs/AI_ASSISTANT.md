# AI Assistant

Open **Tools → AI Assistant…**, then **Connection…**. Choose a provider and enter a text model ID or deployment name available to your account. Studio remembers your model and endpoint on this computer. A key or access token entered in the dialog lasts for the current Studio session. The dialog also shows the environment variable you can set before starting Studio. Credentials and conversations stay out of the project file.

## Try the RC example

1. Select R1 in the schematic and choose **Explain selected circuit**. The **Request** tab shows the exact prompt, device values and pin connections. Choose **Send**. To explain the whole cell, clear the selection and choose **Refresh preview**.
2. Choose **Create a testbench**. For example, enter “Run a transient analysis for 100 µs with a 200 ns step. Probe vin and vout and check that the final output is between 0 and 1.8 V.” Review the request and send it.
3. Review the analysis, stimulus connections, probes and measurements in **Testbench preview**. To change a proposed value or name, edit the JSON in **Answer** and select **Preview testbench**. Choose **Add testbench** to save it. **Analysis → Run saved testbench** runs it with Studio's configured simulator. **Edit → Undo** removes the addition in one step.

A circuit with exposed ports gets a fixture linked to the original circuit. Select a single subcircuit instance to target its circuit definition. For a simple, flat schematic with internal sources and no ports, Studio makes an editable snapshot for the fixture. Later edits to the original standalone circuit require a new snapshot. The preview identifies which form you are adding. Supported analyses are operating point, transient and AC. Fixtures can provide DC or pulse voltage sources, ground connections, resistive or capacitive loads, voltage probes and optional measurement limits.

## Explain a failure

Select a run in the simulation queue, then choose **Explain failed run**. The run picker also includes interrupted jobs and completed runs that missed a measured requirement. The request shows the saved revision, circuit, simulator, failed checks and a limited excerpt from the end of the log. Select another run or choose **Refresh preview** after a new failure. Studio sends the text shown in **Request** when you choose **Send**.

## Connections

| Provider | What to enter |
| --- | --- |
| OpenAI, Anthropic Claude, Google Gemini, Meta, xAI Grok, Mistral, Cohere, DeepSeek | A text model ID and API key for the selected provider. |
| Moonshot Kimi, Z.ai GLM, Baidu Qianfan, NVIDIA, Groq, Perplexity | A model ID from the selected service and its API key. Perplexity uses Agent API model IDs. |
| Alibaba Qwen | Your workspace's regional API base ending in `/compatible-mode/v1`, its key and model ID. |
| Microsoft Azure OpenAI | Your resource URL ending in `/openai/v1`, deployment name and resource API key. |
| Amazon Bedrock | The regional Bedrock runtime URL, model or inference profile ID and a Bedrock bearer API key. Use a model that supports Converse. |
| Google Cloud Vertex AI | The Gemini model collection URL ending in `/v1/projects/PROJECT/locations/LOCATION/publishers/google/models`, publisher model ID and a current OAuth access token. The global host is `aiplatform.googleapis.com`. Regional hosts begin with `LOCATION-aiplatform`. |
| Ollama | Start the local server and enter an installed text model ID. Studio defaults to `http://127.0.0.1:11434/v1`. This also works with locally installed Llama models. |
| OpenAI-compatible endpoint | Enter the server's API base URL, chat model ID and optional key. HTTPS is required for remote hosts. HTTP is supported on loopback. |

Provider setup references include [OpenAI](https://developers.openai.com/api/docs/quickstart), [Claude](https://platform.claude.com/docs/en/api/messages/create), [Gemini](https://ai.google.dev/gemini-api/docs/openai), [Meta](https://dev.meta.ai/docs/cookbook/quickstart-chat-completions), [Perplexity](https://docs.perplexity.ai/docs/agent-api/models), [Qwen](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope), [Azure](https://learn.microsoft.com/en-us/rest/api/aifoundry/azureopenai/chat), [Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-use.html), [Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/docs/start/gcp-auth) and [Ollama](https://docs.ollama.com/api/openai-compatibility).

The assistant tests exercise Studio's menu, preview, cancellation, saved benches and undo with a local HTTP service. The adapter tests cover the request format and text response for every listed provider. These checks support UX-02, UX-10 and EXP-01.
