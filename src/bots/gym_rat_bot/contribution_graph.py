import calendar
import io
from datetime import date

from PIL import Image, ImageDraw, ImageFont

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Colors (tuned for Discord embed background #2b2d31)
EMPTY_COLOR = (55, 58, 64)  # Lighter grey (no check-in)
FILLED_COLOR = (57, 211, 83)  # Green (checked in)
FUTURE_COLOR = (40, 42, 48, 0)  # Transparent (future / padding)
TEXT_COLOR = (255, 255, 255)  # White text
TITLE_COLOR = (255, 255, 255)  # White title

# Layout
CELL_SIZE = 44
CELL_GAP = 6
PADDING = 28
HEADER_HEIGHT = 90  # Space for month title + day labels
DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CORNER_RADIUS = 6


def _round_rect(draw: ImageDraw.Draw, xy, fill, radius):
    """Draw a rounded rectangle."""
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def render_month_calendar(checkin_dates: set[date], year: int, month: int) -> io.BytesIO:
    """Render a monthly calendar as a PNG image. Returns a BytesIO buffer."""
    today = date.today()
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    num_weeks = len(weeks)

    # Calculate image size
    grid_width = 7 * CELL_SIZE + 6 * CELL_GAP
    grid_height = num_weeks * CELL_SIZE + (num_weeks - 1) * CELL_GAP
    img_width = grid_width + 2 * PADDING
    img_height = HEADER_HEIGHT + grid_height + 2 * PADDING

    img = Image.new("RGBA", (img_width, img_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Try to load a nice font, fall back to default
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
        label_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
        day_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except (OSError, IOError):
        try:
            title_font = ImageFont.truetype("DejaVuSans.ttf", 28)
            label_font = ImageFont.truetype("DejaVuSans.ttf", 16)
            day_font = ImageFont.truetype("DejaVuSans.ttf", 14)
        except (OSError, IOError):
            title_font = ImageFont.load_default()
            label_font = title_font
            day_font = title_font

    # Draw month title
    title = f"{MONTH_NAMES[month]} {year}"
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_x = (img_width - (title_bbox[2] - title_bbox[0])) // 2
    draw.text((title_x, PADDING), title, fill=TITLE_COLOR, font=title_font)

    # Draw day labels
    label_y = PADDING + 50
    for i, label in enumerate(DAY_LABELS):
        x = PADDING + i * (CELL_SIZE + CELL_GAP)
        label_bbox = draw.textbbox((0, 0), label, font=label_font)
        label_w = label_bbox[2] - label_bbox[0]
        draw.text(
            (x + (CELL_SIZE - label_w) // 2, label_y),
            label,
            fill=TEXT_COLOR,
            font=label_font,
        )

    # Draw calendar grid
    grid_top = PADDING + HEADER_HEIGHT

    for week_idx, week in enumerate(weeks):
        for day_idx, day_num in enumerate(week):
            x = PADDING + day_idx * (CELL_SIZE + CELL_GAP)
            y = grid_top + week_idx * (CELL_SIZE + CELL_GAP)

            if day_num == 0:
                color = FUTURE_COLOR
            else:
                d = date(year, month, day_num)
                if d > today:
                    color = FUTURE_COLOR
                elif d in checkin_dates:
                    color = FILLED_COLOR
                else:
                    color = EMPTY_COLOR

            _round_rect(draw, [x, y, x + CELL_SIZE, y + CELL_SIZE], fill=color, radius=CORNER_RADIUS)

            # Draw day number on the cell
            if day_num > 0:
                day_str = str(day_num)
                day_bbox = draw.textbbox((0, 0), day_str, font=day_font)
                dw = day_bbox[2] - day_bbox[0]
                dh = day_bbox[3] - day_bbox[1]
                draw.text(
                    (x + (CELL_SIZE - dw) // 2, y + (CELL_SIZE - dh) // 2),
                    day_str,
                    fill=TEXT_COLOR,
                    font=day_font,
                )

    # Save to buffer
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
