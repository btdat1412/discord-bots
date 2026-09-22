"""Declarative building blocks for a Secret Santa edition.

An *edition* is one year's worth of rules: the form people fill in when they
join, who is allowed to read each answer, how participants are matched, and the
wording of every embed. Editions are plain data, so a new year is a new file in
``editions/`` rather than a change to the bot logic.

Nothing here touches Discord or the database — see ``views.py`` for the form
rendering and ``queries.py`` for persistence.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Union

# Discord hard limits.
MAX_FORM_FIELDS = 5  # components per modal
MAX_SELECT_OPTIONS = 25


class FieldStyle(str, Enum):
    """Shape of the text input inside the join modal."""

    SHORT = "short"
    PARAGRAPH = "paragraph"


class Visibility(str, Enum):
    """Who is allowed to read a participant's answer.

    Directions are described from the point of view of the person who wrote the
    answer:

    ``TO_SANTA``
        Readable by the participant assigned to give *you* a gift. This is the
        classic wishlist direction — you write what you want, your (unknown)
        Secret Santa reads it.
    ``TO_TARGET``
        Readable by the participant *you* were assigned to give a gift to. Use
        it for an anonymous note that travels along with the gift. Be aware this
        leaks a little information: the receiver learns something their santa
        wrote.
    ``PUBLIC``
        Shown to everyone in the participants list.
    ``PUBLIC_OPT_IN``
        Shown to the santa always, and to everyone only if the participant
        opts in after joining.
    ``PRIVATE``
        Stored for the record, never shown by the bot.
    """

    TO_SANTA = "to_santa"
    TO_TARGET = "to_target"
    PUBLIC = "public"
    PUBLIC_OPT_IN = "public_opt_in"
    PRIVATE = "private"


class MatchStrategy(str, Enum):
    """How participants are paired up when the host starts the exchange."""

    CIRCLE = "circle"
    """One big random cycle: everyone gives once and receives once, and nobody
    gets themselves. Two people can never end up giving to each other unless
    there are exactly two participants."""

    PAIRS = "pairs"
    """Mutual pairs: A gives to B and B gives to A. Requires an even number of
    participants — good for a swap, e.g. trading T-shirts."""


@dataclass(frozen=True)
class FormField:
    """A free-text input in the join modal, and the rules for its answer."""

    key: str
    """Stable identifier. Stored as a JSON key, so never rename it for an
    edition that has already been played."""

    label: str
    """Shown above the input. Discord caps this at 45 characters."""

    visibility: Visibility = Visibility.TO_SANTA
    style: FieldStyle = FieldStyle.PARAGRAPH
    required: bool = False
    max_length: int = 500
    placeholder: str = ""

    description: Optional[str] = None
    """Smaller helper line under the label. Discord caps it at 100 characters."""

    # Wording used when the answer is rendered in an embed.
    display_label: Optional[str] = None
    """Heading for the answer in the assignment DM / participants list.
    Defaults to ``label``."""

    empty_text: Optional[str] = None
    """Shown instead of the answer when the participant left it blank. When
    ``None`` the field is simply omitted."""

    def heading(self) -> str:
        return self.display_label or self.label


@dataclass(frozen=True)
class SelectField:
    """A dropdown in the join modal. Same answer rules as :class:`FormField`.

    ``options`` are plain strings used as both the value and the visible label,
    so whatever is picked is exactly what gets stored and shown back.
    """

    key: str
    label: str
    options: List[str]

    visibility: Visibility = Visibility.TO_SANTA
    required: bool = True
    placeholder: str = ""
    description: Optional[str] = None
    display_label: Optional[str] = None
    empty_text: Optional[str] = None

    def heading(self) -> str:
        return self.display_label or self.label


Field = Union[FormField, SelectField]


@dataclass(frozen=True)
class Copy:
    """Every remaining player-visible string, so an edition can be written in
    one language end to end.

    Defaults are Vietnamese, matching the server this bot runs on. Override
    only what a given year words differently:

        copy=Copy(shuffling="🔀 **Đang xáo trộn** — check DM nhé.")

    Braces are format placeholders — keep the ones a default already uses.
    """

    # Lobby embed
    participants: str = "Người tham gia"
    joined: str = "{count} người đã tham gia"
    host: str = "Chủ xị"
    how_it_works: str = "Chơi như thế nào"
    important_label: str = "⚠️ Lưu ý"
    important_text: str = (
        "Chỉ **chủ xị** mới bắt đầu được. Người khác bấm cũng không ăn thua."
    )
    not_ready_label: str = "⏳ Chưa đủ người"
    not_ready_text: str = (
        "Cần thêm {missing} người nữa chủ xị mới bắt đầu được."
    )

    # Completed lobby embed
    completed_title: str = "{title} — xong!"
    completed_description: str = (
        "Đã chia xong hết rồi.\n\n"
        "• ✅ Bot đã DM cho từng người\n"
        "• 🤫 Giữ bí mật nhé\n"
        "• 👀 Vẫn xem được danh sách người tham gia\n"
        "• 🔁 Lỡ mất DM? Dùng `/santa-my-assignment` (chỉ mình bạn thấy), "
        "hoặc nhắn tin riêng cho bot"
    )
    status_label: str = "Trạng thái"
    status_completed: str = "🏁 Đã xong"
    completed_footer: str = "{footer} • Đã xong"

    # Participants list
    participants_title: str = "👥 Người tham gia"
    participants_empty: str = "Chưa ai tham gia. Vô đầu tiên đi!"
    participants_footer: str = "Trang {page}/{pages} • Tổng {total} người"
    view_button_label: str = "Xem người tham gia"

    # Join flow
    joined_ok: str = "✅ Vô rồi nha. Chúc may mắn!"
    left_ok: str = "👋 Bạn đã rời game."
    left_with_proxies_ok: str = (
        "👋 Bạn đã rời game. {count} người bạn đăng ký dùm cũng rời theo: "
        "{names}.\nMuốn quay lại thì tham gia rồi đăng ký dùm lại cho họ nhé."
    )
    already_played: str = "❌ Game này chơi xong rồi."
    not_enough: str = (
        "❌ Cần ít nhất {needed} người, hiện mới có {count}."
    )
    draw_running: str = "⏳ Đang bốc thăm rồi, chờ xíu."

    # Start flow
    shuffling: str = "🔀 **Đang xáo trộn** — check DM nhé."
    started_channel: str = (
        "🎉 **{title} bắt đầu!**\n\n"
        "✅ Cả {count} người đã nhận được DM\n"
        "🤫 Giữ bí mật nhé!"
    )
    started_host: str = "✅ Đã bắt đầu. Gửi {count} DM và lưu xong."
    start_failed_host: str = (
        "❌ Game chưa bắt đầu được. Chi tiết ở trong channel — "
        "**không ai nhận được gì cả.**"
    )

    # All-or-nothing failure reports
    preflight_dm: str = (
        "🔒 Đang kiểm tra xem bot nhắn được cho bạn không — kết quả sẽ tới "
        "ngay sau đây."
    )
    unreachable_title: str = (
        "❌ **Chưa bắt đầu được — bot không nhắn được cho:**"
    )
    unreachable_help: str = (
        "Nhờ họ bật **User Settings → Content & Social → Allow direct "
        "messages from server members** (hoặc bỏ chặn bot), rồi bấm bắt đầu "
        "lại.\n**Mọi DM đã gửi đều bị xoá lại, chưa ai được chia và chưa lưu "
        "gì hết.**\nNếu còn người khác cũng tắt DM thì lần sau bot báo tiếp."
    )
    cleanup_failed_note: str = (
        "⚠️ Có DM xoá không được — vài người có thể đã kịp thấy phần cũ. "
        "Coi log trước khi bắt đầu lại."
    )
    generic_failure: str = "❌ **Chưa bắt đầu được.** {reason}"

    # "Register dùm" — entering someone who is not in the Discord server
    proxy_button_label: str = "Đăng ký dùm"
    proxy_modal_title: str = "Đăng ký dùm cho người khác"
    proxy_name_label: str = "Tên của họ"
    proxy_name_placeholder: str = "Ghi rõ họ tên để không ai nhầm"
    proxy_panel_title: str = "📮 Những người bạn đăng ký dùm"
    proxy_panel_description: str = (
        "Đây là những người bạn đăng ký dùm. Họ chơi bình thường như mọi "
        "người — kết quả của họ bot sẽ DM cho **bạn**, bạn báo lại cho họ."
    )
    proxy_panel_empty: str = "Bạn chưa đăng ký dùm cho ai."
    proxy_add_button: str = "➕ Đăng ký thêm người"
    proxy_remove_button: str = "Xoá {name}"
    proxy_registered_ok: str = (
        "✅ Đã đăng ký dùm cho **{name}**. Kết quả của họ bot sẽ DM cho bạn."
    )
    proxy_removed: str = "🗑️ Đã xoá **{name}**."
    proxy_gone: str = "❌ Người này không còn trong danh sách nữa."
    proxy_list_marker: str = "{mention} đăng ký dùm"
    proxy_name_required: str = "❌ Phải ghi tên của họ."

    # The separate DM a registrar gets for each person they registered
    proxy_dm_title: str = "📮 Phần của {name} — bạn đăng ký dùm"
    proxy_dm_intro: str = (
        "Bạn đăng ký dùm cho **{name}**. Đây là phần của **họ**, không phải "
        "của bạn — nhớ báo lại cho họ, đừng nhầm với DM phần của bạn nhé."
    )
    proxy_dm_footer: str = "🤫 Nhớ báo lại cho {name} nha!"

    # Looking your assignment up again by DMing the bot
    dm_lookup_intro: str = (
        "Đây là phần của bạn ở ván gần nhất. Nhắn cho mình bất cứ lúc nào để "
        "xem lại nhé."
    )
    dm_lookup_none: str = (
        "Mình chưa thấy bạn có phần nào ở ván nào đã xong cả.\n"
        "Nếu ván chưa bắt đầu thì chờ chủ xị bấm bắt đầu nha."
    )

    # Pushing the lobby back to the bottom of a busy channel
    bumped_ok: str = "✅ Đã đẩy lobby xuống cuối channel: {link}"

    # Pagination and generic errors
    prev_page: str = "◀️ Trước"
    next_page: str = "Sau ▶️"
    form_error: str = "❌ Có lỗi khi lưu câu trả lời. Thử lại nhé."

    # Opt-in prompt
    opt_in_title: str = "Notes của bạn cho ai xem?"
    opt_in_private_label: str = "🔒 Riêng tư"
    opt_in_private_text: str = "Chỉ người tặng quà cho bạn đọc được"
    opt_in_public_label: str = "🔓 Công khai"
    opt_in_public_text: str = "Ai bấm Xem người tham gia cũng đọc được"
    opt_in_footer: str = "Chọn một cái bên dưới"
    opt_in_saved: str = "✅ Câu trả lời của bạn giờ là **{visibility}**."
    opt_in_public_word: str = "công khai"
    opt_in_private_word: str = "riêng tư"


@dataclass(frozen=True)
class Edition:
    """A complete, self-contained set of rules for one run of the game."""

    key: str
    """Stable identifier stored on every game row, e.g. ``"2026"``. Never
    reuse a key for different rules — old games are replayed through it."""

    year: int
    title: str
    """Headline of the lobby embed, e.g. ``"🎁 Secret Santa 2026"``."""

    command_description: str
    """Shown in the Discord command picker for this edition's choice."""

    form: List[Field]

    lobby_description: str
    """Body of the lobby embed. Explains this year's rules in your own words."""

    how_it_works: str
    """Value of the "How it works" field on the lobby embed."""

    assignment_title: str = "🎁 Phần của bạn đây!"
    assignment_line: str = "Bạn sẽ tặng quà cho: **{target}**"
    """Template for the first line of the assignment DM. ``{target}`` is the
    display name of the person you were matched with."""

    proxy_assignment_line: str = "**{name}** sẽ tặng quà cho: **{target}**"
    """Same as :attr:`assignment_line`, but for the copy of an assignment that
    goes to whoever registered ``{name}`` on their behalf."""

    santa_note_heading: str = "✉️ Lời nhắn từ người tặng quà cho bạn"
    """Heading for answers with :attr:`Visibility.TO_TARGET`."""

    assignment_footer: str = "🤫 Giữ bí mật nhé!"

    match_strategy: MatchStrategy = MatchStrategy.CIRCLE
    min_participants: int = 2

    thumbnail_url: Optional[str] = None
    lobby_color: int = 0xE91E63
    assignment_color: int = 0xE91E63
    completed_color: int = 0x4CAF50

    join_button_label: str = "Tham gia / Rời đi"
    start_button_label: str = "⚠️ CHỈ CHỦ XỊ: Bắt đầu"
    modal_title: str = "Tham gia đổi quà"

    opt_in_prompt: str = "Bạn có muốn cho mọi người xem câu trả lời của mình không?"
    """Shown after joining when the form has a ``PUBLIC_OPT_IN`` field."""

    footer: str = "Secret Santa"

    copy: Copy = Copy()
    """Everything else the players read. See :class:`Copy`."""

    def __post_init__(self) -> None:
        if not self.form:
            raise ValueError(f"edition {self.key}: form must have at least one field")
        if len(self.form) > MAX_FORM_FIELDS:
            raise ValueError(
                f"edition {self.key}: Discord modals accept at most "
                f"{MAX_FORM_FIELDS} inputs, got {len(self.form)}"
            )
        keys = [f.key for f in self.form]
        if len(keys) != len(set(keys)):
            raise ValueError(f"edition {self.key}: duplicate field keys in form")
        for entry in self.form:
            if isinstance(entry, SelectField):
                if not entry.options:
                    raise ValueError(
                        f"edition {self.key}: select '{entry.key}' has no options"
                    )
                if len(entry.options) > MAX_SELECT_OPTIONS:
                    raise ValueError(
                        f"edition {self.key}: select '{entry.key}' has "
                        f"{len(entry.options)} options, Discord allows "
                        f"{MAX_SELECT_OPTIONS}"
                    )
        if self.match_strategy is MatchStrategy.PAIRS and self.min_participants % 2:
            raise ValueError(
                f"edition {self.key}: PAIRS matching needs an even "
                f"min_participants, got {self.min_participants}"
            )

    # ---------- Field lookups used by the embed builders ----------

    def fields_for(self, *visibilities: Visibility) -> List[Field]:
        wanted = set(visibilities)
        return [f for f in self.form if f.visibility in wanted]

    @property
    def santa_fields(self) -> List[Field]:
        """Answers the person gifting you is allowed to read."""
        return self.fields_for(
            Visibility.TO_SANTA, Visibility.PUBLIC, Visibility.PUBLIC_OPT_IN
        )

    @property
    def target_fields(self) -> List[Field]:
        """Answers the person you are gifting is allowed to read."""
        return self.fields_for(Visibility.TO_TARGET)

    @property
    def always_public_fields(self) -> List[Field]:
        return self.fields_for(Visibility.PUBLIC)

    @property
    def opt_in_fields(self) -> List[Field]:
        return self.fields_for(Visibility.PUBLIC_OPT_IN)

    @property
    def has_opt_in(self) -> bool:
        return bool(self.opt_in_fields)
