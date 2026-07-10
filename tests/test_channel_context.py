import unittest

from openclaw_lifecycle import (
    ChannelContextError,
    CurrentChannelContext,
    resolve_current_channel_context,
)


class CurrentChannelContextTests(unittest.TestCase):
    def test_resolves_openclaw_discord_delivery_metadata(self):
        context = resolve_current_channel_context(
            {
                "chat_id": "channel:111111111111111111",
                "conversation_label": (
                    "#openclaw-project-lifecycle-state "
                    "channel id:111111111111111111"
                ),
                "group_channel": "#openclaw-project-lifecycle-state",
                "group_space": "222222222222222222",
            },
            {
                "source": "discord",
                "type": "channel_metadata",
                "payload": {
                    "topic": (
                        "Project channel for OpenClaw project lifecycle state files "
                        "and Discord channel-name rollout automation."
                    )
                },
            },
        )

        self.assertEqual(
            context,
            CurrentChannelContext(
                channel_id="111111111111111111",
                channel_name="openclaw-project-lifecycle-state",
                guild_id="222222222222222222",
                topic=(
                    "Project channel for OpenClaw project lifecycle state files "
                    "and Discord channel-name rollout automation."
                ),
            ),
        )

    def test_prefers_explicit_channel_id(self):
        context = resolve_current_channel_context(
            {
                "channel_id": "111111111111111111",
                "chat_id": "channel:111111111111111111",
                "group_channel": "#example",
            }
        )

        self.assertEqual(context.channel_id, "111111111111111111")
        self.assertEqual(context.channel_name, "example")

    def test_accepts_label_channel_id_fallback(self):
        context = resolve_current_channel_context(
            {
                "conversation_label": "#example channel id:111111111111111111",
                "group_subject": "#example",
            }
        )

        self.assertEqual(context.channel_id, "111111111111111111")
        self.assertEqual(context.channel_name, "example")

    def test_accepts_flat_channel_metadata(self):
        context = resolve_current_channel_context(
            {"chat_id": "channel:111111111111111111"},
            {"topic": "Flat topic"},
        )

        self.assertEqual(context.topic, "Flat topic")

    def test_rejects_missing_channel_id(self):
        with self.assertRaises(ChannelContextError):
            resolve_current_channel_context({"group_channel": "#example"})

    def test_rejects_invalid_channel_id(self):
        with self.assertRaises(ChannelContextError):
            resolve_current_channel_context({"channel_id": "not-a-channel"})

    def test_rejects_invalid_guild_id(self):
        with self.assertRaises(ChannelContextError):
            resolve_current_channel_context(
                {
                    "chat_id": "channel:111111111111111111",
                    "group_space": "workspace-not-snowflake",
                }
            )


if __name__ == "__main__":
    unittest.main()
