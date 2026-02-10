#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time    : 2025/3/18 17:58
# @Author  : Arrow
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from biz.platforms.github.webhook_handler import PullRequestHandler, PushHandler


class TestPushHandler(TestCase):
    def setUp(self):
        self.sample_webhook_data = {
            'repository': {
                'full_name': 'owner/repo'
            },
            'ref': 'refs/heads/main',
            'commits': [
                {
                    'id': 'sample_commit_id',
                    'message': 'Sample commit message',
                    'author': {
                        'name': 'Test Author'
                    },
                    'timestamp': '2023-01-01T12:00:00Z',
                    'url': 'https://github.com/owner/repo/commit/sample_commit_id'
                }
            ]
        }
        self.github_token = ''
        self.github_url = 'https://github.com'
        self.handler = PushHandler(self.sample_webhook_data, self.github_token, self.github_url)

    @patch('biz.platforms.github.webhook_handler.requests.get')
    def test_get_parent_commit_id(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'parents': [{'sha': 'parent_commit_sha'}]}
        mock_get.return_value = mock_response

        parent_id = self.handler.get_parent_commit_id('sample_commit_id')
        self.assertEqual(parent_id, 'parent_commit_sha')


class TestPullRequestHandler(TestCase):
    def setUp(self):
        self.sample_webhook_data = {
            'repository': {
                'full_name': 'owner/repo'
            },
            'pull_request': {
                'number': 99,
                'head': {
                    'sha': 'head_commit_sha'
                }
            },
            'action': 'opened'
        }
        self.handler = PullRequestHandler(self.sample_webhook_data, 'token', 'https://github.com')

    def test_split_review_to_comments(self):
        review_result = """Auto Review Result:
### 问题描述和优化建议
1. 缺少异常处理，建议补充并记录错误上下文。
2. 变量命名可读性较差，建议改为语义化命名。

### 评分明细
- 功能实现: 36/40
总分: 82分
"""
        comments = self.handler._split_review_to_comments(review_result)
        self.assertEqual(
            comments,
            [
                '缺少异常处理，建议补充并记录错误上下文。',
                '变量命名可读性较差，建议改为语义化命名。'
            ]
        )

    def test_extract_review_positions(self):
        changes = [
            {
                'new_path': 'biz/demo.py',
                'diff': '@@ -1,2 +1,4 @@\n line1\n+line2\n+line3\n-line4'
            }
        ]
        positions = self.handler._extract_review_positions(changes)
        self.assertEqual(
            positions,
            [
                {'path': 'biz/demo.py', 'line': 2},
                {'path': 'biz/demo.py', 'line': 3},
            ]
        )

    @patch('biz.platforms.github.webhook_handler.requests.post')
    def test_add_pull_request_notes_posts_inline_comments(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = 'ok'
        mock_post.return_value = mock_response

        changes = [
            {
                'new_path': 'biz/demo.py',
                'diff': '@@ -10,2 +10,4 @@\n line10\n+added11\n+added12\n line13'
            }
        ]
        review_result = 'Auto Review Result:\n1. 第一条建议\n2. 第二条建议'

        self.handler.add_pull_request_notes(review_result, changes=changes)

        self.assertEqual(mock_post.call_count, 2)
        first_call = mock_post.call_args_list[0]
        second_call = mock_post.call_args_list[1]

        self.assertIn('/pulls/99/comments', first_call.args[0])
        self.assertIn('/pulls/99/comments', second_call.args[0])

        self.assertEqual(first_call.kwargs['json']['body'], '第一条建议')
        self.assertEqual(second_call.kwargs['json']['body'], '第二条建议')
        self.assertEqual(first_call.kwargs['json']['path'], 'biz/demo.py')
        self.assertEqual(first_call.kwargs['json']['line'], 11)
        self.assertEqual(second_call.kwargs['json']['line'], 12)


if __name__ == '__main__':
    main()
