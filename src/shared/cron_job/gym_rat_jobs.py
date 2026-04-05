import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from src.shared.job_manager import JobConfig, vietnam_time

log = logging.getLogger(__name__)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


async def daily_gym_reminder(bot: commands.Bot, channel_id: int, **kwargs):
    try:
        channel = bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await bot.fetch_channel(channel_id)
            except Exception:
                log.error("📅 Cannot find channel with ID %s", channel_id)
                return

        log.info("📅 Sending daily gym reminder to channel %s", channel.name)
        await channel.send(
            "Hôm nay mấy con ghệ nhớ điểm danh đấy nhé 💪\n"
            "Dùng `/checkin` hoặc `!gymrat checkin` để điểm danh!"
        )

        # Legit check — find slackers who skipped 3+ days
        gym_rat = getattr(bot, "gym_rat_bot", None)
        if not gym_rat or not gym_rat.db.ready:
            log.warning("📅 Gym Rat DB not ready, skipping legit check")
            return

        from src.bots.gym_rat_bot import queries

        today = datetime.now(VN_TZ).date()

        # Get members currently in the gym channel
        # For text channels, get members who can see the channel
        channel_members = channel.members  # people who can see this channel
        # Filter out bots
        channel_members = [m for m in channel_members if not m.bot]

        if not channel_members:
            log.info("📅 No members in gym channel, skipping legit check")
            return

        found = 0
        for member in channel_members:
            # Check their last check-in
            user = await queries.get_or_create_user(
                gym_rat.db, member.id, member.display_name
            )
            total = await queries.get_total_checkins(gym_rat.db, user["id"])

            # Skip if they've never checked in (new member)
            if total == 0:
                continue

            current_streak, _ = await queries.get_streak(gym_rat.db, user["id"], today)

            # Get last check-in date
            checkins = await queries.get_checkins_range(
                gym_rat.db, user["id"],
                today - timedelta(days=30), today,
            )
            if checkins:
                last_checkin = max(checkins)
                days_missed = (today - last_checkin).days
            else:
                # No check-in in last 30 days, find the actual last one
                all_checkins = await queries.get_checkins_range(
                    gym_rat.db, user["id"],
                    today - timedelta(days=365), today,
                )
                if all_checkins:
                    last_checkin = max(all_checkins)
                    days_missed = (today - last_checkin).days
                else:
                    continue

            # Only flag if 3+ days missed
            if days_missed < 3:
                continue

            embed = discord.Embed(
                title="⚠️ Gym Legit Check",
                description=(
                    f"**{member.display_name}** đã **{days_missed} ngày** không điểm danh!\n"
                    f"Lần cuối check-in: **{last_checkin.strftime('%d/%m/%Y')}**\n\n"
                    f"Kick con ghệ này hay không?\n"
                    f"👍 = Kick | 👎 = Tha"
                ),
                color=discord.Color.red(),
            )

            msg = await channel.send(embed=embed)
            await msg.add_reaction("👍")
            await msg.add_reaction("👎")
            found += 1

        if found == 0:
            log.info("📅 No slackers found, everyone is legit 💪")
        else:
            log.info("📅 Legit check done, found %d slacker(s)", found)

    except Exception as e:
        log.exception("📅 Error in daily gym reminder: %s", e)


def create_daily_reminder_job(channel_id: int) -> JobConfig:
    return JobConfig(
        name="daily_gym_reminder",
        description="Daily gym reminder at 7:00 AM Vietnam time",
        schedule_time=vietnam_time(7, 0),
        job_function=daily_gym_reminder,
        kwargs={"channel_id": channel_id},
    )
