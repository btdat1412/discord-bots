import asyncio
import logging
import re
from typing import Optional, Tuple

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)


class TiGiaBot:

    VCB_URL = (
        "https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx?b=10"
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._register_slash()

    # ---------------- Commands ----------------
    def _register_slash(self) -> None:
        @self.bot.slash_command(
            name="ti-gia", description="Xem tỉ giá USD/VND (VCB) và giá vàng SJC"
        )
        async def ti_gia(interaction: discord.Interaction):
            await interaction.response.defer(thinking=True)
            try:
                embed = await self.execute_ti_gia()
                log.info("💬 Sending response to Discord...")
                await interaction.followup.send(embed=embed)
            except Exception as e:
                log.exception("Error in /ti-gia")
                await interaction.followup.send(f"Đã xảy ra lỗi: {e}")

    async def execute_ti_gia(
        self, title: str = "Tỉ giá & Giá vàng", footer: Optional[str] = None
    ) -> discord.Embed:

        try:
            usd_task = self._fetch_vcb_usd()
            gold_task = self._fetch_sjc_gold()

            usd, gold = await asyncio.gather(
                usd_task, gold_task, return_exceptions=True
            )

            usd_text = (
                self._format_usd_text(usd)
                if not isinstance(usd, Exception)
                else f"❌ VCB lỗi: {usd}"
            )
            gold_text = (
                self._format_gold_text(gold)
                if not isinstance(gold, Exception)
                else f"❌ SJC lỗi: {gold}"
            )

            embed = discord.Embed(
                title=title,
                description="Nguồn: Vietcombank, SJC",
                color=discord.Color.gold(),
            )
            embed.add_field(
                name="💵 USD/VND (Vietcombank)", value=usd_text, inline=False
            )
            embed.add_field(name="🏅 Giá vàng SJC", value=gold_text, inline=False)

            if footer:
                embed.set_footer(text=footer)

            return embed

        except Exception as e:
            log.exception("Error in execute_ti_gia")
            # Return error embed
            error_embed = discord.Embed(
                title="❌ Lỗi",
                description=f"Đã xảy ra lỗi: {e}",
                color=discord.Color.red(),
            )
            return error_embed

    # ---------------- Fetchers ----------------
    async def _fetch_vcb_usd(self) -> Tuple[str, str, str]:
        """
        Returns tuple (buy, transfer, sell) for USD at Vietcombank.
        VCB API commonly returns JSON like:
          {"Exrate":[{"CurrencyCode":"USD","Buy":"24,xxx","Transfer":"24,xxx","Sell":"25,xxx"}, ...]}
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(self.VCB_URL, timeout=15) as resp:

                resp.raise_for_status()
                # Try to parse as JSON first
                try:
                    data = await resp.json(content_type=None)

                    return self._parse_vcb_json(data)
                except Exception as json_error:
                    log.warning("🏦 Failed to parse as JSON: %s", json_error)

                # Try to parse as XML
                try:
                    text = await resp.text()
                    return self._parse_vcb_xml(text)
                except Exception as xml_error:
                    log.error("🏦 Failed to parse as XML: %s", xml_error)
                    raise RuntimeError(
                        f"Cannot parse VCB response as JSON or XML: {json_error}, {xml_error}"
                    )

    def _parse_vcb_json(self, data) -> Tuple[str, str, str]:
        """Parse VCB JSON response"""

        exrates = data.get("Exrate") or data.get("exrate") or []

        for i, row in enumerate(exrates):
            code = row.get("CurrencyCode") or row.get("@CurrencyCode")
            if code and code.upper() == "USD":
                buy = row.get("Buy") or row.get("@Buy") or ""
                transfer = row.get("Transfer") or row.get("@Transfer") or ""
                sell = row.get("Sell") or row.get("@Sell") or ""

                log.info(
                    "🏦 Found USD - Buy: %s, Transfer: %s, Sell: %s",
                    buy,
                    transfer,
                    sell,
                )
                return (buy, transfer, sell)
        raise RuntimeError("Không tìm thấy USD trong JSON VCB")

    def _parse_vcb_xml(self, xml_text: str) -> Tuple[str, str, str]:
        """Parse VCB XML response"""
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(xml_text)

            # Try different XML structures
            for exrate in root.findall(".//Exrate") + root.findall(".//exrate"):
                currency = exrate.get("CurrencyCode") or (
                    exrate.find("CurrencyCode").text
                    if exrate.find("CurrencyCode") is not None
                    else None
                )
                if currency and str(currency).upper() == "USD":
                    buy = exrate.get("Buy") or (
                        exrate.find("Buy").text
                        if exrate.find("Buy") is not None
                        else ""
                    )
                    transfer = exrate.get("Transfer") or (
                        exrate.find("Transfer").text
                        if exrate.find("Transfer") is not None
                        else ""
                    )
                    sell = exrate.get("Sell") or (
                        exrate.find("Sell").text
                        if exrate.find("Sell") is not None
                        else ""
                    )
                    log.info(
                        "🏦 Found USD in XML - Buy: %s, Transfer: %s, Sell: %s",
                        buy,
                        transfer,
                        sell,
                    )
                    return (buy, transfer, sell)

            raise RuntimeError("Không tìm thấy USD trong XML VCB")
        except ET.ParseError as e:
            log.error("🏦 XML Parse Error: %s", e)
            raise RuntimeError(f"Cannot parse XML: {e}")

    async def _fetch_sjc_gold(self) -> Tuple[str, str]:
        """
        Fetch SJC gold prices via vnappmob API.
        Returns tuple (buy_1l, sell_1l) for 1 lượng gold.
        """
        # Get API token
        token_url = "https://api.vnappmob.com/api/request_api_key?scope=gold"

        async with aiohttp.ClientSession() as session:
            async with session.get(token_url, timeout=15) as resp:
                resp.raise_for_status()
                token_data = await resp.json()
                token = token_data.get("results")
                if not token:
                    raise RuntimeError("Không lấy được token từ vnappmob API")

        #  Get gold prices with token
        gold_url = "https://api.vnappmob.com/api/v2/gold/sjc"
        headers = {"Authorization": f"Bearer {token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(gold_url, headers=headers, timeout=15) as resp:
                resp.raise_for_status()
                gold_data = await resp.json()

                results = gold_data.get("results", [])
                if not results:
                    raise RuntimeError("Không có dữ liệu giá vàng từ API")

                data = results[0]  # Get first result
                buy_1l = data.get("buy_1l", "")
                sell_1l = data.get("sell_1l", "")

                if not buy_1l or not sell_1l:
                    raise RuntimeError("Không tìm thấy giá mua/bán 1 lượng")

                # Format prices (remove all decimal places)
                buy_formatted = self._format_price(str(buy_1l))
                sell_formatted = self._format_price(str(sell_1l))

                log.info(
                    "🥇 SJC Gold 1L - Buy: %s, Sell: %s", buy_formatted, sell_formatted
                )
                return (buy_formatted, sell_formatted)

    # ---------------- Formatting ----------------
    def _format_usd_text(self, usd_tuple: Tuple[str, str, str]) -> str:
        buy, transfer, sell = usd_tuple
        # Clean up decimal places and format
        buy_clean = self._format_price(buy)
        transfer_clean = self._format_price(transfer)
        sell_clean = self._format_price(sell)
        return f"**Mua:** {buy_clean}\n**Bán:** {sell_clean}\n**Chuyển khoản:** {transfer_clean}\n"

    def _format_gold_text(self, gold_tuple: Tuple[str, str]) -> str:
        buy, sell = gold_tuple
        # Format numbers with thousand separators
        buy_formatted = self._format_price(buy)
        sell_formatted = self._format_price(sell)
        return (
            f"**1 Lượng**\n**Mua:** {buy_formatted} VND\n**Bán:** {sell_formatted} VND"
        )

    def _format_price(self, price: str) -> str:
        """Format price with thousand separators and remove decimal places"""
        try:
            # Remove any existing thousand separators
            clean_price = price.replace(",", "")

            # Handle decimal places - remove .0, .00, .000, etc.
            if "." in clean_price:
                integer_part, decimal_part = clean_price.split(".", 1)
                # Check if decimal part is all zeros
                if decimal_part and all(c == "0" for c in decimal_part):
                    clean_price = integer_part
                else:
                    # Keep non-zero decimals but this shouldn't happen for currency
                    clean_price = clean_price

            # Convert to int and add thousand separators
            if clean_price.isdigit():
                return f"{int(clean_price):,}"

            # Fallback for non-numeric strings
            return price.replace(".0", "").replace(".00", "").replace(".000", "")
        except:
            # Ultimate fallback - just remove common decimal patterns
            return price.replace(".0", "").replace(".00", "").replace(".000", "")

    # ---------------- Utils ----------------
    @staticmethod
    def _is_price(x: Optional[str]) -> bool:
        if not x:
            return False
        # accept formats like 88,800; 88.800; 88800; 88,800,000 etc.
        return bool(re.fullmatch(r"[0-9][0-9\.,]*", x))


# Entry point expected by your loader:
def setup(bot: commands.Bot) -> None:
    TiGiaBot(bot)
