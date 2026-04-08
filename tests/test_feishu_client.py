from __future__ import annotations

import unittest
from unittest.mock import patch

from poco.platform.feishu.client import (
    FeishuAccessTokenProvider,
    FeishuMessageClient,
)


class FeishuClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.token_provider = FeishuAccessTokenProvider(
            base_url="https://open.feishu.cn",
            app_id="cli_test",
            app_secret="secret",
        )
        self.client = FeishuMessageClient(
            base_url="https://open.feishu.cn",
            token_provider=self.token_provider,
        )

    def test_create_group_chat_uses_feishu_chat_api(self) -> None:
        with (
            patch.object(self.token_provider, "get_token", return_value="tenant-token"),
            patch("poco.platform.feishu.client._post_json") as post_json,
        ):
            post_json.return_value = {
                "code": 0,
                "data": {
                    "chat_id": "oc_group_123",
                    "name": "PoCo | Demo",
                },
            }

            result = self.client.create_group_chat(
                name="PoCo | Demo",
                owner_open_id="ou_demo_user",
            )

        self.assertEqual(result.chat_id, "oc_group_123")
        self.assertEqual(result.name, "PoCo | Demo")
        kwargs = post_json.call_args.kwargs
        self.assertIn("/open-apis/im/v1/chats?", kwargs["url"])
        self.assertIn("user_id_type=open_id", kwargs["url"])
        self.assertIn("set_bot_manager=true", kwargs["url"])
        self.assertEqual(kwargs["payload"]["name"], "PoCo | Demo")
        self.assertEqual(kwargs["payload"]["owner_id"], "ou_demo_user")
        self.assertEqual(kwargs["payload"]["chat_mode"], "group")
        self.assertEqual(kwargs["payload"]["chat_type"], "private")
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer tenant-token",
        )


if __name__ == "__main__":
    unittest.main()
