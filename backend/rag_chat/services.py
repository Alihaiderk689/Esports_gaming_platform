import anthropic
from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

from rag_chat.models import ChatMessage, Rule

MODEL = 'claude-opus-4-8'
MAX_HISTORY_MESSAGES = 20
MAX_CONTEXT_RULES = 5


class ChatNotConfigured(Exception):
    pass


def retrieve_relevant_rules(query_text):
    search_query = SearchQuery(query_text)
    vector = SearchVector('title', weight='A') + SearchVector('content', weight='B')
    return list(
        Rule.objects.annotate(rank=SearchRank(vector, search_query))
        .filter(rank__gt=0)
        .order_by('-rank')[:MAX_CONTEXT_RULES]
    )


def _build_system_prompt(rules):
    if not rules:
        return (
            'You are a helpful assistant for an esports tournament platform. No specific '
            'platform rules matched this question. If the question needed rule documentation, '
            'say plainly that you do not have specific rules on this topic rather than guessing.'
        )
    rules_text = '\n\n'.join(f'### {rule.title}\n{rule.content}' for rule in rules)
    return (
        "You are a helpful assistant for an esports tournament platform. Answer the user's "
        'question using ONLY the following platform rules as your source of truth. If the '
        'rules do not cover the question, say so explicitly rather than guessing.\n\n'
        f'{rules_text}'
    )


def get_chat_response(user, message_text):
    if not settings.ANTHROPIC_API_KEY:
        raise ChatNotConfigured('ANTHROPIC_API_KEY is not set.')

    history = list(ChatMessage.objects.filter(user=user).order_by('-created_at')[:MAX_HISTORY_MESSAGES])
    history.reverse()

    rules = retrieve_relevant_rules(message_text)
    system_prompt = _build_system_prompt(rules)

    messages = [{'role': m.role, 'content': m.content} for m in history]
    messages.append({'role': 'user', 'content': message_text})

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )
    reply_text = next((block.text for block in response.content if block.type == 'text'), '')
    return reply_text, rules
