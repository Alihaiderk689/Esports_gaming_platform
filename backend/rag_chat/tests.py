from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from games.models import Game
from rag_chat.models import ChatHistory, RuleBook
from rag_chat.services.chroma_service import _game_where
from rag_chat.services.game_detector import detect_game, detect_games

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
        resp = self.client.post('/api/chat/', {'message': 'When do I need to check in for a Valorant match?'})

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['question'], 'When do I need to check in for a Valorant match?')
        self.assertEqual(resp.data['answer'], 'You must check in 15 minutes before your match.')

        chat = ChatHistory.objects.get(user=self.user)
        self.assertEqual(chat.question, 'When do I need to check in for a Valorant match?')
        self.assertEqual(chat.answer, 'You must check in 15 minutes before your match.')
        self.assertEqual(chat.game_name, 'Valorant')

        mock_generate_answer.assert_called_once_with(
            'When do I need to check in for a Valorant match?', 'Check in 15 minutes before.', history=[],
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
        mock_retrieve.return_value = ([], 'Valorant')
        mock_rerank.return_value = []
        mock_build_context.return_value = ''
        mock_generate_answer.return_value = 'Answer for other user.'

        self.client.force_authenticate(user=self.other_user)
        self.client.post('/api/chat/', {'message': 'A Valorant question only other_user asked'})

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
        resp = self.client.post('/api/chat/', {'message': 'Tell me about Valorant match rules'})
        self.assertEqual(resp.status_code, 503)
        self.assertFalse(ChatHistory.objects.filter(user=self.user).exists())

    @patch('rag_chat.views.retrieve_candidates')
    def test_chat_ambiguous_question_asks_for_clarification_instead_of_guessing(self, mock_retrieve):
        # No game named in the question, and no prior conversation turn to
        # fall back on — retrieving unscoped here risks confidently answering
        # from the wrong game's rulebook, so this must short-circuit before
        # ever touching retrieval/embeddings/Groq, not just eventually
        # produce a vague answer.
        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/chat/', {'message': 'How many players are there?'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('which game', resp.data['answer'].lower())
        mock_retrieve.assert_not_called()
        self.assertFalse(ChatHistory.objects.filter(user=self.user).exists())

    @patch('rag_chat.views.retrieve_candidates')
    def test_chat_ambiguous_question_lists_known_games_as_examples(self, mock_retrieve):
        Game.objects.create(name='Tekken 8', slug='tekken-8')
        Game.objects.create(name='PUBG Mobile', slug='pubg-mobile')

        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/chat/', {'message': 'What is the prize for winning?'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('Tekken 8', resp.data['answer'])
        self.assertIn('PUBG Mobile', resp.data['answer'])
        mock_retrieve.assert_not_called()

    @patch('rag_chat.views.generate_answer')
    @patch('rag_chat.views.build_context')
    @patch('rag_chat.views.rerank')
    @patch('rag_chat.views.retrieve_candidates')
    def test_chat_question_naming_two_games_is_not_treated_as_ambiguous(
        self, mock_retrieve, mock_rerank, mock_build_context, mock_generate_answer,
    ):
        # Naming two games is a different situation from naming none — this
        # must still run retrieval (scoped to both, see
        # RetrievalMultiGameTests), not get treated as unanswerable.
        mock_retrieve.return_value = ([{'text': '[Tekken 8] ...'}, {'text': '[PUBG Mobile] ...'}], 'Tekken 8')
        mock_rerank.return_value = [{'text': '[Tekken 8] ...'}, {'text': '[PUBG Mobile] ...'}]
        mock_build_context.return_value = '[Tekken 8] ...\n\n[PUBG Mobile] ...'
        mock_generate_answer.return_value = 'Tekken 8 has X, PUBG Mobile has Y.'

        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/chat/', {'message': 'Compare Tekken 8 and PUBG Mobile match lengths'})

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        mock_retrieve.assert_called_once()


class GameDetectorMultiGameTests(TestCase):
    def setUp(self):
        # "Tekken"/"PUBG" are only canonicalized into "Tekken 8"/"PUBG Mobile"
        # (see game_detector._canonical_name_map) when those longer names
        # actually exist as catalog Game rows — without them, the raw alias
        # from _COMMON_ESPORTS_GAMES is returned as-is.
        Game.objects.create(name='Tekken 8', slug='tekken-8')
        Game.objects.create(name='PUBG Mobile', slug='pubg-mobile')

    def test_detect_games_finds_every_game_mentioned(self):
        games = detect_games('Compare Tekken 8 and PUBG Mobile substitution rules')
        self.assertIn('Tekken 8', games)
        self.assertIn('PUBG Mobile', games)

    def test_detect_games_ranks_most_mentioned_first(self):
        games = detect_games('Valorant Valorant Valorant and Tekken')
        self.assertEqual(games[0], 'Valorant')

    def test_detect_games_empty_for_no_known_game(self):
        self.assertEqual(detect_games('How many players are there?'), [])

    def test_detect_games_deduplicates_alias_and_canonical_name(self):
        # "Tekken" is an alias baked into _COMMON_ESPORTS_GAMES; "Tekken 8" is
        # the platform's own catalog name for the same game — mentioning both
        # forms must merge into one entry, not two.
        games = detect_games('Tekken 8 rules, also just Tekken in general')
        self.assertEqual(games.count('Tekken 8'), 1)

    def test_detect_game_still_returns_single_best_guess(self):
        # Back-compat: existing single-game callers (chunk_service.py tagging
        # one rulebook section) still get one value, not a list.
        self.assertEqual(detect_game('Tekken 8 match rules'), 'Tekken 8')
        self.assertIsNone(detect_game('How many players are there?'))


class ChromaGameWhereTests(TestCase):
    def test_none_or_empty_produces_no_filter(self):
        self.assertIsNone(_game_where(None))
        self.assertIsNone(_game_where(''))
        self.assertIsNone(_game_where([]))

    def test_single_string_produces_equality_filter(self):
        self.assertEqual(_game_where('Tekken 8'), {'game_name': 'Tekken 8'})

    def test_single_item_list_produces_equality_filter_not_in(self):
        self.assertEqual(_game_where(['Tekken 8']), {'game_name': 'Tekken 8'})

    def test_multiple_games_produce_in_filter(self):
        self.assertEqual(
            _game_where(['Tekken 8', 'PUBG Mobile']),
            {'game_name': {'$in': ['Tekken 8', 'PUBG Mobile']}},
        )


class RetrieveCandidatesMultiGameTests(TestCase):
    def setUp(self):
        # See GameDetectorMultiGameTests.setUp — canonicalization to the full
        # catalog name only happens when that catalog row actually exists.
        Game.objects.create(name='Tekken 8', slug='tekken-8')
        Game.objects.create(name='PUBG Mobile', slug='pubg-mobile')

    @patch('rag_chat.services.retrieval_service.keyword_query')
    @patch('rag_chat.services.retrieval_service.vector_query')
    @patch('rag_chat.services.retrieval_service.generate_embeddings')
    def test_question_naming_two_games_scopes_query_to_both(
        self, mock_embeddings, mock_vector_query, mock_keyword_query,
    ):
        from rag_chat.services.retrieval_service import retrieve_candidates

        mock_embeddings.return_value = [[0.1, 0.2]]
        mock_vector_query.return_value = []
        mock_keyword_query.return_value = []

        retrieve_candidates('Compare Tekken 8 and PUBG Mobile substitution rules')

        game_scope = mock_vector_query.call_args.kwargs['game_name']
        self.assertIsInstance(game_scope, list)
        self.assertIn('Tekken 8', game_scope)
        self.assertIn('PUBG Mobile', game_scope)

    @patch('rag_chat.services.retrieval_service.keyword_query')
    @patch('rag_chat.services.retrieval_service.vector_query')
    @patch('rag_chat.services.retrieval_service.generate_embeddings')
    def test_single_game_question_scopes_to_one_game_not_a_list(
        self, mock_embeddings, mock_vector_query, mock_keyword_query,
    ):
        from rag_chat.services.retrieval_service import retrieve_candidates

        mock_embeddings.return_value = [[0.1, 0.2]]
        mock_vector_query.return_value = []
        mock_keyword_query.return_value = []

        _, effective_game = retrieve_candidates('What are the Tekken 8 match rules?')

        self.assertEqual(mock_vector_query.call_args.kwargs['game_name'], 'Tekken 8')
        self.assertEqual(effective_game, 'Tekken 8')

    @patch('rag_chat.services.retrieval_service.keyword_query')
    @patch('rag_chat.services.retrieval_service.vector_query')
    @patch('rag_chat.services.retrieval_service.generate_embeddings')
    def test_no_game_named_falls_back_to_previous_turns_game(
        self, mock_embeddings, mock_vector_query, mock_keyword_query,
    ):
        from rag_chat.services.retrieval_service import retrieve_candidates

        mock_embeddings.return_value = [[0.1, 0.2]]
        mock_vector_query.return_value = []
        mock_keyword_query.return_value = []

        _, effective_game = retrieve_candidates('What about substitutes?', fallback_game='Tekken 8')

        self.assertEqual(mock_vector_query.call_args.kwargs['game_name'], 'Tekken 8')
        self.assertEqual(effective_game, 'Tekken 8')
