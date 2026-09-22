# Secret Santa Bot

A gift-exchange bot that runs inside this framework. Ported from the standalone
Go bot (`secret-santa-2025`), with two things it did not have:

- **All-or-nothing delivery.** Either every participant receives their
  assignment, or nobody does and nothing is saved.
- **Editions.** Each year is a config file. Rules, form fields, wording and the
  matching algorithm change per year, and old games stay readable.
- **Register dùm.** People who are not in the Discord server can still play.

---

## 1. Create the Discord bot

You need a separate bot application for Secret Santa (one token per bot in this
framework).

1. Open <https://discord.com/developers/applications> and click
   **New Application**. Name it, e.g. `Secret Santa`.
2. Left sidebar → **Bot**.
   - Click **Reset Token**, then **Copy**. This is `SECRET_SANTA_BOT_TOKEN`.
     It is shown once — paste it into `.env` now.
   - Scroll to **Privileged Gateway Intents** and enable **SERVER MEMBERS
     INTENT**. The bot needs it to read server nicknames.
     Leave *Message Content Intent* off — this bot does not read messages.
3. Left sidebar → **Installation** (on older portals: **OAuth2 → URL
   Generator**).
   - **Scopes**: `bot`, `applications.commands`
   - **Bot permissions**: `Send Messages`, `Embed Links`,
     `Read Message History`, `Use Slash Commands`
   - Copy the generated install URL.
4. Open that URL, pick your server, authorise.
5. Tell your members to allow DMs from the server, otherwise the bot cannot
   deliver assignments: **User Settings → Content & Social → Allow direct
   messages from server members**. (The bot checks this before drawing and
   refuses to start if anyone is unreachable, so nobody gets a half-finished
   game.)

## 2. Configure

Add to `.env` (see `.env.example`):

```bash
SECRET_SANTA_BOT_TOKEN=...
SECRET_SANTA_DATABASE_URL=postgresql://user:password@host:port/dbname
```

Every bot names its own DSN, so any one of them can be moved to a separate
database later without touching the others. Sharing one instance just means
giving two of them the same value.

The bot creates its own tables on first connect and has its own migrations
directory, so it can share a PostgreSQL instance with the other bots or use a
separate one. All its tables are prefixed `santa_`, and migration filenames are
unique across the repo, which is what makes the shared `_migrations` table
safe. Concurrent migrations are serialised with a PostgreSQL advisory lock,
since the bots start as parallel processes.

Then run the framework as usual:

```bash
python -m src.app
```

Slash commands are synced per guild on startup, so they appear within seconds.

## 3. Playing

| Command | Who | What |
|---|---|---|
| `/secret-santa [edition]` | anyone | Opens a lobby. Without `edition` it uses the current year's rules. |
| `/santa-history` | anyone | Past games in this server: edition, host, participant count, state. |
| `/santa-my-assignment` | anyone | Re-shows your assignment from the latest finished game, in case the DM is lost. The reply is ephemeral, so nobody else sees the command or the answer. |
| `/my-current-game` | anyone | Reposts the open lobby at the bottom of the channel, so nobody has to scroll for it. |

**Or just DM the bot.** Any direct message to it — literally any text — gets
your assignment back. Slash commands are synced per guild and therefore do not
exist in DMs, so a plain message is the one thing that always works there. It
reads nothing but the fact that a DM arrived, so no Message Content intent is
needed. There is a 5-second per-user cooldown.

In the lobby: **Join / Leave** opens the form (click it again to leave, then
join again to redo your answers), **View Participants** lists who is in,
**Đăng ký dùm** enters someone who is not in the server, and **Start** —
visible only once enough people have joined, and only working for the host —
draws and DMs everyone.

### Keeping the lobby findable

A lobby posted on Monday is unreachable by Wednesday in a chatty channel.
`/my-current-game` posts a fresh copy at the bottom, and a daily job does the
same every morning (08:00 Vietnam time, `SECRET_SANTA_BUMP_HOUR` to change it,
registered under `secret-santa` in `BOT_CRON_MAPPINGS`).

A game can therefore be on screen several times at once, so **every copy is
live**: `santa_lobby_messages` lists them, `_refresh_lobby` edits all of them
on every join or leave, and each gets its own `View` instance because
discord.py binds a persistent view to a single message id. Copies that were
deleted in Discord are dropped from the table on the next refresh.

A bump deletes the previous pushed-down copy first, so a channel gains at most
one lobby message per game no matter how often it runs. The original message
from `/secret-santa` is never deleted.

### Register dùm — playing without a Discord account

Press **Đăng ký dùm** and fill in their name plus the normal form. They become
a full participant: they are drawn like everyone else, they can be assigned to
anyone, and anyone can be assigned to them.

Because they have no account to message, **their assignment is DM'd to you**,
as its own message with its own title and an intro line saying whose it is —
never merged into your own assignment DM. You pass it on to them.

Press the button again to see everyone you entered, add another, or remove one.
There is no edit: remove and re-add. Only the member who entered someone can
remove them.

**Leaving takes them with you.** If you press Join / Leave to drop out, everyone
you registered drops out too — they have no account of their own, so with no
registrar there is nobody to deliver their assignment to. Rejoining means
registering them again.

Under the hood a proxy is an ordinary participant row whose `user_id` is
`proxy:<random hex>` instead of a Discord snowflake, with `registered_by`
pointing at you. `queries.is_proxy()` is the only check needed anywhere.

If *you* have DMs closed, the preflight names you and the game will not start —
your proxies' assignments have nowhere to go either.

## 4. Adding next year

1. Copy `editions/edition_2026.py` to `editions/edition_<year>.py`.
2. Change `key`, `year`, the wording, and the `form`.
3. Register it in `editions/__init__.py`: import it and add it to `_ALL`.

Never edit an edition that has already been played — old games are re-rendered
through their stored `edition_key`, so changing it rewrites history. Make a new
edition instead.

### The form

One entry per input in the join modal. **Discord allows at most 5 components**,
and the edition refuses to load if you exceed that. The register-dùm form
spends one of those five on the name box, so keep the form at **4 fields or
fewer** — a fifth would be dropped from that form (with a warning in the logs).

`FormField` is free text:

```python
FormField(
    key="size_note",            # stored as a JSON key — never rename it later
    label="Notes về size",      # above the input (Discord cuts at 45 chars)
    display_label="📝 Notes",    # heading when the answer is shown back
    placeholder="Kiểu thích gì thì ghi vô",
    style=FieldStyle.PARAGRAPH, # or SHORT for a one-line box
    visibility=Visibility.TO_SANTA,
    required=False,
    max_length=500,
    empty_text="*Không ghi gì.*",  # or None to hide the field when blank
)
```

`SelectField` is a dropdown. The strings in `options` are used as both the
value and the label, so what gets picked is exactly what gets stored (max 25):

```python
SelectField(
    key="shirt_size",
    label="Chọn size áo cho bạn",
    display_label="📏 Size áo",
    placeholder="Chọn size của bạn",
    options=["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"],
    required=True,
    visibility=Visibility.TO_SANTA,
)
```

Dropdowns work inside a modal because each component is wrapped in a
`discord.ui.Label` (discord.py 2.6+). Requires nothing extra from you.

### The rest of the wording

Everything else players read — field headings on the lobby embed, the
"shuffling" message, the DM-blocked report, button labels — lives in a `Copy`
block on the edition, with English defaults. Override only what you want:

```python
copy=Copy(
    participants="Người tham gia",
    host="Chủ xị",
    shuffling="🔀 **Đang xáo trộn** — check DM nhé.",
)
```

Defaults are Vietnamese, so a new edition usually overrides only the few lines
its own theme words differently (`edition_2026.py` overrides four). Braces in a
default (`{count}`, `{missing}`, `{title}`, `{name}`) are format placeholders —
keep them in your replacement.

### Who sees an answer

`visibility` answers exactly one question: **who may read what I wrote?**

| Value | Readable by |
|---|---|
| `TO_SANTA` | The person assigned to give **you** a gift. This is the wishlist direction — it is what makes your input reach whoever has to buy for you. |
| `TO_TARGET` | The person **you** were assigned to give to. Use it for an anonymous note that travels with the gift. |
| `PUBLIC` | Everyone, in View Participants. |
| `PUBLIC_OPT_IN` | Your santa always; everyone else only if you press **Public** after joining. |
| `PRIVATE` | Nobody. Stored for the record only. |

A note on `TO_TARGET`: the receiver learns something their santa wrote. It does
not name them, but it is a small leak — skip it if you want strict anonymity.

### Matching

| `match_strategy` | Behaviour |
|---|---|
| `MatchStrategy.CIRCLE` | One random cycle across everyone. Each person gives once and receives once, and nobody draws themselves. Mutual pairs cannot happen except with exactly 2 players. |
| `MatchStrategy.PAIRS` | Mutual pairs — A and B give to each other. Requires an even number of participants; the bot refuses to start otherwise and says so. |

2026 uses `CIRCLE`: you give to one person and receive from a different,
unknown one.

`min_participants` gates the Start button.

## 5. How "all-or-nothing" works

Discord has no transactions, so `exchange.py` builds the closest honest
equivalent:

1. **Preflight** — a short probe DM goes to everyone who has to be messaged.
   Opening a DM channel succeeds even for people who block DMs (this is exactly
   what the old Go bot got wrong), so an actual send is the only proof of
   reachability. If anyone fails, the probes are deleted and the run stops
   before a single assignment exists — nobody sees anything.
2. **Deliver** — assignment DMs go out, each message remembered.
3. **Undo on failure** — if someone passed the probe and then refused the
   assignment anyway, every DM already sent is deleted. The database has not
   been touched at all, so there is nothing else to unwind.
4. **Commit** — only once every DM has landed: assignments, the delivery log
   and the new game state in a single transaction.

Because the draw is saved last, a game marked `COMPLETED` always means everyone
was notified. The failure path reports who could not be reached and confirms
nothing was saved; if a sent DM could not be deleted again, it says so too,
since somebody may have glimpsed an assignment that no longer counts.

The probe costs one extra DM per person per start attempt. That is the price of
the guarantee: without it, whoever is early in the delivery order would receive
an assignment that a later failure has to take back.

## 6. Schema

Four tables, created by the files in `migrations/`:

- `santa_games` — one row per lobby, carrying `edition_key`.
- `santa_participants` — one row per player per game. Answers live in a JSONB
  column keyed by field key, so **a new year never needs a migration**.
  `registered_by` is set for people entered through "register dùm".
- `santa_deliveries` — the DM log, written with the commit.
- `santa_lobby_messages` — every message currently showing a game's buttons.

## 7. Files

```
src/bots/secret_santa_bot/
├── __init__.py      setup(bot): wires the DB and re-arms open lobbies
├── bot.py           slash commands and interaction handlers
├── models.py        Edition / FormField / SelectField / Visibility / Copy
├── editions/        one file per year + the registry
├── matching.py      the pairing algorithms (pure functions)
├── exchange.py      the all-or-nothing start sequence
├── queries.py       SQL
├── ui.py            embed builders, all wording from the edition
├── views.py         buttons and the join modal
└── migrations/      schema
```
