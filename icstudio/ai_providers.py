"""Text inference across Studio's supported providers. No vendor SDK or account is required at startup."""
import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import quote, urlsplit


@dataclass(frozen=True)
class Provider:
    name: str
    base: str
    env: str = ''
    dialect: str = 'chat'
    configurable: bool = False
    hint: str = ''


PROVIDERS = {
    'openai': Provider('OpenAI', 'https://api.openai.com/v1', 'OPENAI_API_KEY', 'responses'),
    'anthropic': Provider('Anthropic Claude', 'https://api.anthropic.com/v1', 'ANTHROPIC_API_KEY', 'anthropic'),
    'gemini': Provider('Google Gemini', 'https://generativelanguage.googleapis.com/v1beta/openai', 'GEMINI_API_KEY'),
    'meta': Provider('Meta', 'https://api.meta.ai/v1', 'MODEL_API_KEY'),
    'xai': Provider('xAI Grok', 'https://api.x.ai/v1', 'XAI_API_KEY'),
    'mistral': Provider('Mistral AI', 'https://api.mistral.ai/v1', 'MISTRAL_API_KEY'),
    'cohere': Provider('Cohere', 'https://api.cohere.ai/compatibility/v1', 'COHERE_API_KEY'),
    'deepseek': Provider('DeepSeek', 'https://api.deepseek.com', 'DEEPSEEK_API_KEY'),
    'qwen': Provider('Alibaba Qwen', '', 'DASHSCOPE_API_KEY', configurable=True,
                     hint='Paste your Alibaba Cloud workspace base URL ending in /compatible-mode/v1'),
    'perplexity': Provider('Perplexity', 'https://api.perplexity.ai/v1', 'PERPLEXITY_API_KEY', 'perplexity'),
    'kimi': Provider('Moonshot Kimi', 'https://api.moonshot.ai/v1', 'MOONSHOT_API_KEY'),
    'zai': Provider('Z.ai GLM', 'https://api.z.ai/api/paas/v4', 'ZAI_API_KEY'),
    'baidu': Provider('Baidu Qianfan', 'https://api.baiduqianfan.ai/v1', 'QIANFAN_API_KEY'),
    'nvidia': Provider('NVIDIA', 'https://integrate.api.nvidia.com/v1', 'NVIDIA_API_KEY'),
    'groq': Provider('Groq', 'https://api.groq.com/openai/v1', 'GROQ_API_KEY'),
    'azure': Provider('Microsoft Azure OpenAI', '', 'AZURE_OPENAI_API_KEY', configurable=True,
                      hint='https://RESOURCE.openai.azure.com/openai/v1'),
    'bedrock': Provider('Amazon Bedrock', 'https://bedrock-runtime.us-east-1.amazonaws.com',
                        'AWS_BEARER_TOKEN_BEDROCK', 'bedrock', True, 'Regional Bedrock runtime URL'),
    'vertex': Provider('Google Cloud Vertex AI', '', 'GOOGLE_CLOUD_ACCESS_TOKEN', 'vertex', True,
                       'https://aiplatform.googleapis.com/v1/projects/PROJECT/locations/global/publishers/google/models'),
    'ollama': Provider('Ollama (local models)', 'http://127.0.0.1:11434/v1', configurable=True),
    'custom': Provider('OpenAI-compatible endpoint', '', configurable=True, hint='https://your-server.example/v1'),
}


def endpoint(provider, base):
    profile = PROVIDERS[provider]
    base = base.strip().rstrip('/')
    if not base or len(base) > 1024 or re.search(r'[\s\\?#@{}<>]', base):
        raise ValueError('Enter an API base URL without a password, query, or fragment.')
    parsed = urlsplit(base)
    host = parsed.hostname or ''
    if parsed.port == 0:
        raise ValueError('Choose a valid TCP port.')
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host == 'localhost'
    if not host or not (parsed.scheme == 'https' or (local and parsed.scheme == 'http')):
        raise ValueError('Use HTTPS, or HTTP on a loopback address for a local model.')
    if not profile.configurable and base != profile.base:
        raise ValueError('Use the official provider endpoint.')
    allowed = {
        'azure': r'[a-z0-9-]+\.(?:openai\.azure\.com|services\.ai\.azure\.com)',
        'bedrock': r'bedrock-runtime\.[a-z0-9-]+\.amazonaws\.com(?:\.cn)?',
        'vertex': r'(?:[a-z0-9-]+-)?aiplatform\.googleapis\.com',
        'qwen': r'(?:[a-z0-9-]+\.[a-z0-9-]+\.maas|dashscope(?:-[a-z0-9-]+)?)\.aliyuncs\.com',
    }
    if provider in allowed and (not re.fullmatch(allowed[provider], host) or parsed.port not in (None, 443)):
        raise ValueError('Use the official resource or regional endpoint for this provider.')
    paths = {'azure': '/openai/v1', 'bedrock': '', 'vertex': r'/v1/projects/[a-zA-Z0-9-]+/locations/[a-z0-9-]+/publishers/google/models',
             'qwen': '/compatible-mode/v1'}
    if provider in paths and not re.fullmatch(paths[provider], parsed.path):
        raise ValueError('Check the API base URL format shown for this provider.')
    return base


def request_parts(provider, base, model, token, prompt):
    profile = PROVIDERS[provider]
    base = endpoint(provider, base)
    model = model.strip()
    if not model or len(model) > 512 or any(ord(c) < 32 for c in model) or model in ('.', '..'):
        raise ValueError('Enter a model ID or deployment name from your provider.')
    if profile.env and not token:
        raise ValueError('Enter a credential in Connection or set ' + profile.env + '.')
    if token and (not token.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in token)):
        raise ValueError('The credential contains spaces or invalid characters.')
    headers = {'Content-Type': 'application/json'}
    if token:
        if provider == 'anthropic':
            headers.update({'x-api-key': token, 'anthropic-version': '2023-06-01'})
        elif provider == 'azure':
            headers['api-key'] = token
        else:
            headers['Authorization'] = 'Bearer ' + token
    messages = [{'role': 'user', 'content': prompt}]
    if profile.dialect == 'responses':
        return base + '/responses', headers, dict(model=model, input=prompt, store=False)
    if profile.dialect == 'perplexity':
        return base + '/agent', headers, dict(model=model, input=prompt, tools=[])
    if profile.dialect == 'anthropic':
        return base + '/messages', headers, dict(model=model, max_tokens=4096, messages=messages)
    if profile.dialect == 'bedrock':
        return base + '/model/' + quote(model, safe='') + '/converse', headers, {
            'messages': [{'role': 'user', 'content': [{'text': prompt}]}]}
    if profile.dialect == 'vertex':
        return base + '/' + quote(model, safe='') + ':generateContent', headers, {
            'contents': [{'role': 'user', 'parts': [{'text': prompt}]}]}
    return base + '/chat/completions', headers, dict(model=model, messages=messages)


def response_text(provider, data):
    dialect = PROVIDERS[provider].dialect
    try:
        if dialect in ('responses', 'perplexity'):
            parts = [part['text'] for item in data['output'] if item.get('type') == 'message'
                     for part in item['content'] if part.get('type') == 'output_text']
        elif dialect == 'anthropic':
            parts = [p['text'] for p in data['content'] if p.get('type') == 'text']
        elif dialect == 'bedrock':
            parts = [p['text'] for p in data['output']['message']['content'] if 'text' in p]
        elif dialect == 'vertex':
            parts = [p['text'] for p in data['candidates'][0]['content']['parts'] if 'text' in p and not p.get('thought')]
        else:
            parts = [data['choices'][0]['message']['content']]
        result = '\n'.join(parts).strip()
    except (IndexError, KeyError, TypeError, AttributeError):
        result = ''
    if not result:
        raise ValueError('The provider returned no answer text. Check model access or try another text model.')
    return result
