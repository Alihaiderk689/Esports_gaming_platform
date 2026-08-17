from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from games.models import Game
from rag_chat.models import ChatHistory, RuleBook

User = get_user_model()


class RuleBookApiTests(APITestCase):
    def setUp(self):
        self.game = Game.objects.create(name='Valorant', genre='FPS')
        self.user = User.objects.create_user(email='player@example.com', password='StrongPass123')
        self.admin = User.objects.create_user(email='admin@example.com', password='StrongPass123', is_staff=True)
        self.rulebook = RuleBook.objects.create(
            game=self.game,
            title='Valorant Official Rules',
            pdf_url='https://example.com/rules.pdf',
            public_id='rulebooks/valorant-rules',
            uploaded_by=self.admin,
            is_processed=True,
        )
        self.client.force_authenticate(user=self.user)

    def _results(self, resp):
        return resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data

    def test_list_rulebooks_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/rules/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_rulebooks(self):
        resp = self.client.get('/api/rules/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        titles = {r['title'] for r in self._results(resp)}
        self.assertIn('Valorant Official Rules', titles)

    def test_upload_rulebook_forbidden_for_non_admin(self):
        resp = self.client.post('/api/rules/upload/', {'game': self.game.id, 'title': 'New Rules'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_upload_rulebook_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.post('/api/rules/upload/', {'game': self.game.id, 'title': 'New Rules'})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('rag_chat.views.add_chunks')
    @patch('rag_chat.views.generate_embeddings')
    @patch('rag_chat.views.split_text_into_chunks')
    @patch('rag_chat.views.extract_text_from_pdf')
    @patch('rag_chat.views.upload_pdf')
    def test_upload_rulebook_allowed_for_admin(
        self, mock_upload_pdf, mock_extract_text, mock_split_text, mock_generate_embeddings, mock_add_chunks,
    ):
        mock_upload_pdf.return_value = {'url': 'https://example.com/new.pdf', 'public_id': 'rulebooks/new'}
        mock_extract_text.return_value = 'Rule text.'
        mock_split_text.return_value = [{'text': 'Rule text.'}]
        mock_generate_embeddings.return_value = [[0.1, 0.2]]

        self.client.force_authenticate(user=self.admin)
        pdf = SimpleUploadedFile('rules.pdf', b'%PDF-1.4 fake pdf content', content_type='application/pdf')
        resp = self.client.post(
            '/api/rules/upload/', {'game': self.game.id, 'title': 'New Rules', 'pdf': pdf}, format='multipart',
        )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['title'], 'New Rules')
        rulebook = RuleBook.objects.get(title='New Rules')
        self.assertTrue(rulebook.is_processed)
        mock_add_chunks.assert_called_once()

    def test_delete_rulebook_forbidden_for_non_admin(self):
        resp = self.client.delete(f'/api/rules/{self.rulebook.pk}/delete/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(RuleBook.objects.filter(pk=self.rulebook.pk).exists())

    @patch('rag_chat.views.delete_pdf')
    @patch('rag_chat.views.delete_rulebook')
    def test_delete_rulebook_allowed_for_admin(self, mock_delete_rulebook, mock_delete_pdf):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.delete(f'/api/rules/{self.rulebook.pk}/delete/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(RuleBook.objects.filter(pk=self.rulebook.pk).exists())
        mock_delete_rulebook.assert_called_once_with(self.rulebook.pk)
        mock_delete_pdf.assert_called_once_with(self.rulebook.public_id)


class ChatApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='player@example.com', password='StrongPass123')
        self.other_user = User.objects.create_user(email='other@example.com', password='StrongPass123')

    def test_chat_requires_auth(self):
        resp = self.client.post('/api/chat/', {'message': 'When do I need to check in?'})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_chat_requires_message(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/chat/', {})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('rag_chat.views.generate_answer')
    @patch('rag_chat.views.build_context')
    @patch('rag_chat.views.rerank')
    @patch('rag_chat.views.retrieve_candidates')
    def test_chat_success(self, mock_retrieve, mock_rerank, mock_build_context, mock_generate_answer):
        mock_retrieve.return_value = ([{'text': 'Check in 15 minutes before.'}], 'Valorant')
        mock_rerank.return_value = [{'text': 'Check in 15 minutes before.'}]
        mock_build_context.return_value = 'Check in 15 minutes before.'
        mock_generate_answer.return_value = 'You must check in 15 minutes before your match.'

        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/chat/', {'message': 'When do I need to check in?'})

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['question'], 'When do I need to check in?')
        self.assertEqual(resp.data['answer'], 'You must check in 15 minutes before your match.')

        chat = ChatHistory.objects.get(user=self.user)
        self.assertEqual(chat.question, 'When do I need to check in?')
        self.assertEqual(chat.answer, 'You must check in 15 minutes before your match.')
        self.assertEqual(chat.game_name, 'Valorant')

        mock_generate_answer.assert_called_once_with(
            'When do I need to check in?', 'Check in 15 minutes before.', history=[],
        )

    @patch('rag_chat.views.generate_answer')
    @patch('rag_chat.views.build_context')
    @patch('rag_chat.views.rerank')
    @patch('rag_chat.views.retrieve_candidates')
    def test_chat_includes_prior_history(self, mock_retrieve, mock_rerank, mock_build_context, mock_generate_answer):
        ChatHistory.objects.create(user=self.user, question='Hello', answer='Hi there!', game_name='Valorant')

        mock_retrieve.return_value = ([], 'Valorant')
        mock_rerank.return_value = []
        mock_build_context.return_value = ''
        mock_generate_answer.return_value = 'Follow-up answer.'

        self.client.force_authenticate(user=self.user)
        self.client.post('/api/chat/', {'message': 'Follow-up question'})

        mock_generate_answer.assert_called_once_with(
            'Follow-up question', '', history=[{'question': 'Hello', 'answer': 'Hi there!'}],
        )
        # No game named in this question, so the previous turn's game_name carries forward.
        mock_retrieve.assert_called_once_with('Follow-up question', fallback_game='Valorant')

    @patch('rag_chat.views.generate_answer')
    @patch('rag_chat.views.build_context')
    @patch('rag_chat.views.rerank')
    @patch('rag_chat.views.retrieve_candidates')
    def test_chat_history_isolated_per_user(self, mock_retrieve, mock_rerank, mock_build_context, mock_generate_answer):
        mock_retrieve.return_value = ([], None)
        mock_rerank.return_value = []
        mock_build_context.return_value = ''
        mock_generate_answer.return_value = 'Answer for other user.'

        self.client.force_authenticate(user=self.other_user)
        self.client.post('/api/chat/', {'message': 'A question only other_user asked'})

        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/chat/history/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(self._results(resp)), 0)

    def _results(self, resp):
        return resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data

    def test_chat_history_requires_auth(self):
        resp = self.client.get('/api/chat/history/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('rag_chat.views.retrieve_candidates')
    def test_chat_pipeline_failure_returns_503(self, mock_retrieve):
        # Any exception in the retrieve/rerank/build/generate pipeline (a real
        # Groq auth failure, a Chroma outage, etc.) is caught by the same
        # `except Exception` in ChatView.post — one exception source is
        # representative of the whole code path.
        mock_retrieve.side_effect = Exception('vector store unreachable')

        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/chat/', {'message': 'Hello'})
        self.assertEqual(resp.status_code, 503)
        self.assertFalse(ChatHistory.objects.filter(user=self.user).exists())
