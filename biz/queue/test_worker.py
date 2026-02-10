from unittest import TestCase, main
from unittest.mock import MagicMock, patch

import biz.queue.worker as worker


class TestGithubPullRequestFlow(TestCase):
    def setUp(self):
        self.webhook_data = {
            'action': 'opened',
            'repository': {
                'name': 'repo',
                'full_name': 'owner/repo',
            },
            'pull_request': {
                'head': {
                    'sha': 'head_commit_sha',
                    'ref': 'feature-branch',
                },
                'base': {
                    'ref': 'main',
                },
                'user': {
                    'login': 'alice',
                },
                'html_url': 'https://github.com/owner/repo/pull/99',
            },
        }
        self.github_token = 'token'
        self.github_url = 'https://github.com'
        self.github_url_slug = 'github_com'
        self.changes = [
            {
                'diff': '@@ -1,1 +1,2 @@\n line1\n+line2',
                'new_path': 'biz/demo.py',
                'additions': 1,
                'deletions': 0,
            }
        ]
        self.commits = [
            {
                'title': 'feat: sample',
                'message': 'feat: sample',
            }
        ]
        self.review_result = """### 问题描述和优化建议
1. 建议补充单元测试。

### 评分明细
总分: 82分
"""
        self.approval_decision = {
            'event': 'APPROVE',
            'score': 82,
            'threshold': 80,
            'blockers': [],
            'reason': 'Score reaches threshold and no blocker keywords were detected.',
        }

    @staticmethod
    def _build_mock_handler(changes, commits, approval_decision):
        handler = MagicMock()
        handler.action = 'opened'
        handler.get_pull_request_changes.return_value = changes
        handler.get_pull_request_commits.return_value = commits
        handler.evaluate_approval_decision.return_value = approval_decision
        handler._build_review_body.return_value = 'AI Review Decision: APPROVE'
        return handler

    @patch('biz.queue.worker.ReviewService.check_mr_last_commit_id_exists', return_value=False)
    @patch('biz.queue.worker.CodeReviewer')
    @patch('biz.queue.worker.filter_github_changes')
    @patch('biz.queue.worker.GithubPullRequestHandler')
    @patch('biz.queue.worker.notifier.send_notification')
    def test_handle_github_pull_request_event_calls_submit_after_inline_comments(
        self,
        mock_notify,
        mock_handler_cls,
        mock_filter_changes,
        mock_code_reviewer_cls,
        mock_check_last_commit,
    ):
        handler = self._build_mock_handler(self.changes, self.commits, self.approval_decision)
        mock_handler_cls.return_value = handler
        mock_filter_changes.return_value = self.changes

        mock_reviewer = MagicMock()
        mock_reviewer.review_and_strip_code.return_value = self.review_result
        mock_code_reviewer_cls.return_value = mock_reviewer

        call_order = []

        def add_inline_comments(*args, **kwargs):
            call_order.append('inline')

        def evaluate_decision(*args, **kwargs):
            call_order.append('decision')
            return self.approval_decision

        def build_review_body(*args, **kwargs):
            call_order.append('body')
            return 'AI Review Decision: APPROVE'

        def submit_review(*args, **kwargs):
            call_order.append('submit')

        handler.add_pull_request_notes.side_effect = add_inline_comments
        handler.evaluate_approval_decision.side_effect = evaluate_decision
        handler._build_review_body.side_effect = build_review_body
        handler.submit_pull_request_review.side_effect = submit_review

        mock_signal = MagicMock()
        with patch('biz.queue.worker.event_manager', {'merge_request_reviewed': mock_signal}):
            worker.handle_github_pull_request_event(
                self.webhook_data, self.github_token, self.github_url, self.github_url_slug
            )

        self.assertEqual(call_order, ['inline', 'decision', 'body', 'submit'])
        handler.submit_pull_request_review.assert_called_once_with(
            event='APPROVE', body='AI Review Decision: APPROVE'
        )
        mock_signal.send.assert_called_once()
        mock_notify.assert_not_called()
        mock_check_last_commit.assert_called_once()

    @patch('biz.queue.worker.ReviewService.check_mr_last_commit_id_exists', return_value=False)
    @patch('biz.queue.worker.CodeReviewer')
    @patch('biz.queue.worker.filter_github_changes')
    @patch('biz.queue.worker.GithubPullRequestHandler')
    @patch('biz.queue.worker.notifier.send_notification')
    def test_handle_github_pull_request_event_notifies_when_submit_review_failed(
        self,
        mock_notify,
        mock_handler_cls,
        mock_filter_changes,
        mock_code_reviewer_cls,
        mock_check_last_commit,
    ):
        handler = self._build_mock_handler(self.changes, self.commits, self.approval_decision)
        handler.submit_pull_request_review.side_effect = RuntimeError('submit failed')
        mock_handler_cls.return_value = handler
        mock_filter_changes.return_value = self.changes

        mock_reviewer = MagicMock()
        mock_reviewer.review_and_strip_code.return_value = self.review_result
        mock_code_reviewer_cls.return_value = mock_reviewer

        mock_signal = MagicMock()
        with patch('biz.queue.worker.event_manager', {'merge_request_reviewed': mock_signal}):
            worker.handle_github_pull_request_event(
                self.webhook_data, self.github_token, self.github_url, self.github_url_slug
            )

        handler.add_pull_request_notes.assert_called_once()
        handler.submit_pull_request_review.assert_called_once()
        mock_signal.send.assert_not_called()
        mock_notify.assert_called_once()
        mock_check_last_commit.assert_called_once()


if __name__ == '__main__':
    main()
