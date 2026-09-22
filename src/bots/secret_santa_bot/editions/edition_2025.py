"""2025 edition — ván đổi quà gốc, port từ bot Go.

Giữ lại để xem lại các ván cũ. Không đổi field key.
"""

from ..models import Edition, FieldStyle, FormField, MatchStrategy, Visibility

THUMBNAIL = (
    "https://media.discordapp.net/attachments/1404849489671360626/"
    "1404868135617822811/fate-nero-claudius.png"
)

EDITION = Edition(
    key="2025",
    year=2025,
    title="🎁 Secret Santa 2025",
    command_description="Đổi quà — wishlist và danh sách không muốn",
    modal_title="🎁 Tham gia Secret Santa",
    form=[
        FormField(
            key="wishlist",
            label="Bạn muốn nhận gì? (Không bắt buộc)",
            display_label="💝 Họ muốn",
            placeholder="Để trống thì được tặng gì cũng phải chịu",
            style=FieldStyle.PARAGRAPH,
            visibility=Visibility.PUBLIC_OPT_IN,
            max_length=500,
            empty_text="*Không yêu cầu gì — cứ thoải mái sáng tạo!*",
        ),
        FormField(
            key="avoid_list",
            label="Bạn không muốn nhận gì? (Không bắt buộc)",
            display_label="🚫 Họ không muốn",
            placeholder="Để trống thì được tặng gì cũng phải chịu",
            style=FieldStyle.PARAGRAPH,
            visibility=Visibility.PUBLIC_OPT_IN,
            max_length=500,
        ),
    ],
    lobby_description=(
        "Bấm **Tham gia / Rời đi** để vào hoặc rời game.\n\n"
        "• **Wishlist** và **danh sách không muốn** sẽ được gửi cho người "
        "tặng quà cho bạn\n"
        "• Người tặng làm theo hay không là tuỳ (không bắt buộc)\n"
        "• Cả hai list đều riêng tư, trừ khi bạn chọn công khai\n"
        "• Bấm **Xem người tham gia** để biết ai đã vào\n"
        "• Bấm **Tham gia / Rời đi** hai lần để sửa lại câu trả lời\n\n"
        "🎄 **Merry & Bright!** 🎁"
    ),
    how_it_works=(
        "Khi đủ người, bot sẽ xáo trộn và DM cho bạn biết phải tặng quà cho "
        "ai.\n**Hoàn toàn ngẫu nhiên, không ai setup được.**"
    ),
    assignment_title="🎁 Phần Secret Santa của bạn đây!!!",
    assignment_line="Bạn sẽ tặng quà cho: **{target}**",
    assignment_footer="🤫 Bí mật đó! Đừng nói cho ai biết bạn bốc trúng ai!",
    opt_in_prompt="Bạn có muốn công khai wishlist của mình không?",
    match_strategy=MatchStrategy.CIRCLE,
    min_participants=2,
    thumbnail_url=THUMBNAIL,
    footer="Secret Santa • Pan-chan Edition",
)
