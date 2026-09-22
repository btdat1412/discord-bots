"""2026 edition — ĐỔI QUÀ GAMING 2026, đổi áo in hình customize.

Copy this file to start a new year. Change ``key``, ``year``, and the form.
"""

from ..models import (
    Copy,
    Edition,
    FieldStyle,
    FormField,
    MatchStrategy,
    SelectField,
    Visibility,
)

SHIRT_SIZES = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]

EDITION = Edition(
    key="2026",
    year=2026,
    title="🎮 ĐỔI QUÀ GAMING 2026",
    command_description="Đổi áo in hình customize 2026",
    modal_title="🎮 ĐỔI QUÀ GAMING 2026",
    form=[
        SelectField(
            key="shirt_size",
            label="Size áo",
            display_label="📏 Size áo",
            placeholder="Chọn size",
            options=SHIRT_SIZES,
            required=True,
            visibility=Visibility.TO_SANTA,
        ),
        FormField(
            key="shirt_note",
            label="Notes về áo",
            display_label="👕 Notes về áo",
            placeholder="VD: mặc M hơi chật, thích áo ngắn, dài lưng...",
            style=FieldStyle.PARAGRAPH,
            required=False,
            max_length=500,
            visibility=Visibility.TO_SANTA,
        ),
        FormField(
            key="wishlist",
            label="Bạn muốn nhận gì? (Không bắt buộc)",
            display_label="💝 Họ muốn",
            placeholder="Để trống thì được tặng gì cũng phải chịu",
            style=FieldStyle.PARAGRAPH,
            required=False,
            max_length=500,
            visibility=Visibility.PUBLIC_OPT_IN,
            empty_text="*Không yêu cầu gì — cứ thoải mái sáng tạo!*",
        ),
        FormField(
            key="avoid_list",
            label="Bạn không muốn nhận gì? (Không bắt buộc)",
            display_label="🚫 Họ không muốn",
            placeholder="Để trống thì được tặng gì cũng phải chịu",
            style=FieldStyle.PARAGRAPH,
            required=False,
            max_length=500,
            visibility=Visibility.PUBLIC_OPT_IN,
        ),
    ],
    lobby_description=(
        "**Đổi áo in hình customize 2026**\n\n"
        "Bấm **Tham gia / Rời đi** để vào hoặc rời game.\n\n"
        "**Luật**\n"
        "• Bạn sẽ được phân phối cho 1 người để tặng áo, bạn cũng sẽ được "
        "tặng 1 chiếc áo từ người bí ẩn.\n"
        "• Để giữ gìn sự vui vẻ của trò chơi, xin không tiết lộ bạn sẽ tặng "
        "ai cho người khác.\n"
        "• Áo bạn tặng phải mang được ít nhất 3 lần cho người sử dụng "
        "(không quá lố lăng) nhưng vẫn ở mức đủ tấu hài.\n"
        "• Áo bạn tặng phải đúng size người sử dụng đã nêu rõ, không được cố "
        "tình mua áo quá chật hoặc quá rộng (có thể bỏ qua nếu là lỗi điền "
        "form sai hoặc lỗi của nsx).\n\n"
        "**Wishlist** và **danh sách không muốn** sẽ được gửi cho người tặng "
        "áo cho bạn — riêng tư, trừ khi bạn chọn công khai.\n\n"
        "Bấm **Tham gia / Rời đi** lần nữa để rời, rồi tham gia lại nếu muốn "
        "sửa câu trả lời."
    ),
    how_it_works=(
        "Khi đủ người, bot sẽ xáo trộn và DM cho bạn biết bạn phải tặng áo "
        "cho ai, kèm size, notes và wishlist của người đó.\n"
        "**Hoàn toàn ngẫu nhiên, không ai setup được.**"
    ),
    assignment_title="🎮 Bạn tặng áo cho ai đây!",
    assignment_line="Bạn sẽ tặng áo cho: **{target}**",
    proxy_assignment_line="**{name}** sẽ tặng áo cho: **{target}**",
    assignment_footer="🤫 Giữ bí mật nhé, đừng tiết lộ cho ai!",
    opt_in_prompt="Bạn có muốn công khai wishlist của mình không?",
    match_strategy=MatchStrategy.CIRCLE,
    min_participants=2,
    lobby_color=0x9B59B6,
    assignment_color=0x9B59B6,
    footer="ĐỔI QUÀ GAMING 2026",
    copy=Copy(
        # Chỉ override những chỗ năm nay nói khác mặc định — phần còn lại
        # (lobby, lỗi DM, phân trang...) lấy nguyên từ Copy().
        opt_in_title="Wishlist của bạn cho ai xem?",
        opt_in_private_text="Chỉ người mua áo cho bạn đọc được",
        opt_in_saved="✅ Wishlist của bạn giờ là **{visibility}**.",
        proxy_panel_description=(
            "Đây là những người bạn đăng ký dùm. Họ chơi bình thường như mọi "
            "người — kết quả của họ bot sẽ DM cho **bạn**, bạn báo lại cho họ."
        ),
    ),
)
