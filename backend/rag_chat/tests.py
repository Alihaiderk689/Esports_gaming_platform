from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from rag_chat.models import ChatMessage, Rule

User = get_user_model()


def _mock_claude_response(text):
    block = MagicMock()
    block.type = 'text'
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


class RuleApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='player@example.com', password='StrongPass123')
        self.admin = User.objects.create_user(email='admin@example.com', password='StrongPass123', is_staff=True)
        self.rule = Rule.objects.create(
            title='Check-in policy',
            content='Players must check in 15 minutes before their match.',
            uploaded_by=self.admin,
        )
        self.client.force_authenticate(user=self.user)

    def _results(self, resp):
        return resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data

    def test_list_rules_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/rules/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_rules(self):
        resp = self.client.get('/api/rules/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        titles = {r['title'] for r in self._results(resp)}
        self.assertIn('Check-in policy', titles)

    def test_upload_rule_forbidden_for_non_admin(self):
        resp = self.client.post('/api/upload-rules/', {'title': 'New Rule', 'content': 'Some content.'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_upload_rule_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.post('/api/upload-rules/', {'title': 'New Rule', 'content': 'Some content.'})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_upload_rule_allowed_for_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post('/api/upload-rules/', {'title': 'New Rule', 'content': 'Some content.'})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['uploaded_by_email'], 'admin@example.com')
        self.assertTrue(Rule.objects.filter(title='New Rule').exists())

    def test_delete_rule_forbidden_for_non_admin(self):
        resp = self.client.delete(f'/api/rules/{self.rule.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Rule.objects.filter(pk=self.rule.pk).exists())

    def test_delete_rule_allowed_for_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.delete(f'/api/rules/{self.rule.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Rule.objects.filter(pk=self.rule.pk).exists())


@override_settings(ANTHROPIC_API_KEY='sk-ant-test-key')
class ChatApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='player@example.com', password='StrongPass123')
        self.other_user = User.objects.create_user(email='other@example.com', password='StrongPass123')
        self.admin = User.objects.create_user(email='admin@example.com', password='StrongPass123', is_staff=True)
        Rule.objects.create(
            title='Check-in policy',
            content='Players must check in 15 minutes before their scheduled match time or forfeit their slot.',
            uploaded_by=self.admin,
        )
        self.client.force_authenticate(user=self.user)

    def test_chat_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.post('/api/chat/', {'message': 'When do I need to check in?'})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_chat_requires_message(self):
        resp = self.client.post('/api/chat/', {})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('rag_chat.services.anthropic.Anthropic')
    def test_chat_success(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_claude_response(
            'You must check in 15 minutes before your match.',
        )
        mock_anthropic_cls.return_value = mock_client

        resp = self.client.post('/api/chat/', {'message': 'When do I need to check in?'})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['role'], 'assistant')
        self.assertEqual(resp.data['content'], 'You must check in 15 minutes before your match.')

        messages = list(ChatMessage.objects.filter(user=self.user).order_by('created_at'))
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, 'user')
        self.assertEqual(messages[0].content, 'When do I need to check in?')
        self.assertEqual(messages[1].role, 'assistant')

        # Verify the rule content was actually passed to Claude as system context
        call_kwargs = mock_client.messages.create.call_args.kwargs
        self.assertIn('Check-in policy', call_kwargs['system'])
        self.assertEqual(call_kwargs['model'], 'claude-opus-4-8')

    @patch('rag_chat.services.anthropic.Anthropic')
    def test_chat_includes_prior_history(self, mock_anthropic_cls):
        ChatMessage.objects.create(user=self.user, role=ChatMessage.Role.USER, content='Hello')
        ChatMessage.objects.create(user=self.user, role=ChatMessage.Role.ASSISTANT, content='Hi there!')

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_claude_response('Follow-up answer.')
        mock_anthropic_cls.return_value = mock_client

        self.client.post('/api/chat/', {'message': 'Follow-up question'})

        call_kwargs = mock_client.messages.create.call_args.kwargs
        sent_messages = call_kwargs['messages']
        self.assertEqual(sent_messages[0], {'role': 'user', 'content': 'Hello'})
        self.assertEqual(sent_messages[1], {'role': 'assistant', 'content': 'Hi there!'})
        self.assertEqual(sent_messages[2], {'role': 'user', 'content': 'Follow-up question'})

    @patch('rag_chat.services.anthropic.Anthropic')
    def test_chat_history_isolated_per_user(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_claude_response('Answer for other user.')
        mock_anthropic_cls.return_value = mock_client

        self.client.force_authenticate(user=self.other_user)
        self.client.post('/api/chat/', {'message': 'A question only other_user asked'})

        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/chat/history/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data
        self.assertEqual(len(results), 0)

    def test_chat_history_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/chat/history/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('rag_chat.services.anthropic.Anthropic')
    def test_chat_history_ordered_chronologically(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _mock_claude_response('First answer.'),
            _mock_claude_response('Second answer.'),
        ]
        mock_anthropic_cls.return_value = mock_client

        self.client.post('/api/chat/', {'message': 'First question'})
        self.client.post('/api/chat/', {'message': 'Second question'})

        resp = self.client.get('/api/chat/history/')
        results = resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data
        contents = [m['content'] for m in results]
        self.assertEqual(contents, [
            'First question', 'First answer.', 'Second question', 'Second answer.',
        ])

    def test_chat_missing_api_key_returns_503(self):
        with self.settings(ANTHROPIC_API_KEY=''):
            resp = self.client.post('/api/chat/', {'message': 'Hello'})
        self.assertEqual(resp.status_code, 503)
        self.assertTrue(ChatMessage.objects.filter(user=self.user, role='user', content='Hello').exists())
        self.assertFalse(ChatMessage.objects.filter(user=self.user, role='assistant').exists())

    @patch('rag_chat.services.anthropic.Anthropic')
    def test_chat_authentication_error_returns_503(self, mock_anthropic_cls):
        import anthropic as anthropic_module

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = anthropic_module.AuthenticationError(
            message='invalid key', response=MagicMock(status_code=401, headers={}), body=None,
        )
        mock_anthropic_cls.return_value = mock_client

        resp = self.client.post('/api/chat/', {'message': 'Hello'})
        self.assertEqual(resp.status_code, 503)
        # The user message is still recorded even though the assistant call failed
        self.assertTrue(ChatMessage.objects.filter(user=self.user, role='user', content='Hello').exists())
        self.assertFalse(ChatMessage.objects.filter(user=self.user, role='assistant').exists())
