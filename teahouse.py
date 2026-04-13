     1|#!/usr/bin/env python3
     2|"""teahouse - A thin CLI wrapper around GitHub Discussions GraphQL API."""
     3|
     4|import sys
     5|import os
     6|import json
     7|import urllib.request
     8|import urllib.error
     9|from datetime import datetime, timezone
    10|from pathlib import Path
    11|
    12|# ── Config ──────────────────────────────────────────────────────────────────
    13|
    14|REPO_OWNER = "ythx-101"
    15|REPO_NAME = "openclaw-qa"
    16|GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
    17|STATE_PATH = Path.home() / ".teahouse" / "state.json"
    18|
    19|EXIT_OK = 0
    20|EXIT_NO_TOKEN=***
    21|EXIT_NETWORK = 2
    22|EXIT_GRAPHQL = 3
    23|EXIT_SHORT_ID = 4
    24|
    25|# ── State management ────────────────────────────────────────────────────────
    26|
    27|def load_state():
    28|    if STATE_PATH.exists():
    29|        return json.loads(STATE_PATH.read_text())
    30|    return {"discussions": {}}
    31|
    32|def save_state(state):
    33|    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    34|    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    35|
    36|# ── GraphQL ─────────────────────────────────────────────────────────────────
    37|
    38|def gql(query, variables=None, token=None):
    39|    body = {"query": query}
    40|    if variables:
    41|        body["variables"] = variables
    42|    data = json.dumps(body).encode()
    43|    req = urllib.request.Request(
    44|        GRAPHQL_ENDPOINT,
    45|        data=data,
    46|        headers={
    47|            "Authorization": f"bearer {token}",
    48|            "Content-Type": "application/json",
    49|        },
    50|    )
    51|    try:
    52|        with urllib.request.urlopen(req, timeout=30) as resp:
    53|            result = json.loads(resp.read())
    54|    except urllib.error.HTTPError as e:
    55|        print(f"error: HTTP {e.code}: {e.reason}", file=sys.stderr)
    56|        sys.exit(EXIT_NETWORK)
    57|    except urllib.error.URLError as e:
    58|        print(f"error: network: {e.reason}", file=sys.stderr)
    59|        sys.exit(EXIT_NETWORK)
    60|
    61|    if "errors" in result:
    62|        print(f"error: {result['errors'][0]['message']}", file=sys.stderr)
    63|        sys.exit(EXIT_GRAPHQL)
    64|
    65|    return result["data"]
    66|
    67|# ── Helpers ─────────────────────────────────────────────────────────────────
    68|
    69|def display_width(s):
    70|    """Calculate display width: CJK chars count as 2."""
    71|    w = 0
    72|    for ch in s:
    73|        if '\u4e00' <= ch <= '\u9fff' or '\u3000' <= ch <= '\u303f' or \
    74|           '\uff00' <= ch <= '\uffef' or '\U00020000' <= ch <= '\U0002a6df':
    75|            w += 2
    76|        else:
    77|            w += 1
    78|    return w
    79|
    80|def truncate_display(s, max_width):
    81|    """Truncate string to max display width, adding '..' if needed."""
    82|    w = 0
    83|    result = []
    84|    for ch in s:
    85|        cw = 2 if ('\u4e00' <= ch <= '\u9fff' or '\u3000' <= ch <= '\u303f' or
    86|                    '\uff00' <= ch <= '\uffef' or '\U00020000' <= ch <= '\U0002a6df') else 1
    87|        if w + cw > max_width - 2:
    88|            result.append('..')
    89|            return ''.join(result)
    90|        w += cw
    91|        result.append(ch)
    92|    return ''.join(result)
    93|
    94|def format_time(iso_str):
    95|    """Convert ISO 8601 to 'YYYY-MM-DD HH:MM'."""
    96|    ts = iso_str.replace("Z", "+00:00")
    97|    dt = datetime.fromisoformat(ts)
    98|    return dt.strftime("%Y-%m-%d %H:%M")
    99|
   100|def body_preview(body, max_len=40):
   101|    """First line of body, truncated."""
   102|    first_line = body.split("\n")[0].strip()
   103|    if len(first_line) > max_len:
   104|        return first_line[:max_len] + "..."
   105|    return first_line
   106|
   107|# ── Command: list ───────────────────────────────────────────────────────────
   108|
   109|def cmd_list(token):
   110|    query = """
   111|    query {
   112|      repository(owner: "%s", name: "%s") {
   113|        discussions(first: 50, orderBy: {field: UPDATED_AT, direction: DESC}) {
   114|          nodes {
   115|            number
   116|            title
   117|            updatedAt
   118|          }
   119|        }
   120|      }
   121|    }
   122|    """ % (REPO_OWNER, REPO_NAME)
   123|
   124|    data = gql(query, token=token)
   125|    discussions = data["repository"]["discussions"]["nodes"]
   126|    state = load_state()
   127|
   128|    for d in discussions:
   129|        num = d["number"]
   130|        title = truncate_display(d["title"], 30)
   131|        title_padded = f"{title}".ljust(30 + title.count('..'))
   132|        # Pad to 30 display columns
   133|        dw = display_width(title)
   134|        padding = " " * max(0, 30 - dw)
   135|        title_field = title + padding
   136|
   137|        # Check unread
   138|        disc_state = state["discussions"].get(str(num), {})
   139|        last_read = disc_state.get("last_read_at")
   140|        unread_tag = ""
   141|        if last_read:
   142|            # Count comments newer than last_read
   143|            # We'd need comment counts, but we don't have them here without another query.
   144|            # For now, just check if there was activity after last_read
   145|            updated = d["updatedAt"]
   146|            if updated > last_read:
   147|                # We don't know the exact count without fetching comments,
   148|                # so we just mark it as having updates
   149|                unread_tag = " [新]"
   150|        else:
   151|            unread_tag = " [新]"
   152|
   153|        print(f"{num:>3}  {title_field}{unread_tag}")
   154|
   155|# ── Command: read ───────────────────────────────────────────────────────────
   156|
   157|def cmd_read(token, number, limit=20):
   158|    query = """
   159|    query($number: Int!, $limit: Int!) {
   160|      repository(owner: "%s", name: "%s") {
   161|        discussion(number: $number) {
   162|          id
   163|          title
   164|          url
   165|          comments(last: $limit) {
   166|            nodes {
   167|              id
   168|              author { login }
   169|              createdAt
   170|              body
   171|              replyTo { id author { login } }
   172|              replies(first: 20) {
   173|                nodes {
   174|                  id
   175|                  author { login }
   176|                  createdAt
   177|                  body
   178|                  replyTo { id }
   179|                }
   180|              }
   181|            }
   182|          }
   183|        }
   184|      }
   185|    }
   186|    """ % (REPO_OWNER, REPO_NAME)
   187|
   188|    data = gql(query, variables={"number": number, "limit": limit}, token=token)
   189|    discussion = data["repository"]["discussion"]
   190|
   191|    if not discussion:
   192|        print(f"error: discussion #{number} not found", file=sys.stderr)
   193|        sys.exit(EXIT_GRAPHQL)
   194|
   195|    title = discussion["title"]
   196|    url = discussion["url"]
   197|    comments = discussion["comments"]["nodes"]
   198|
   199|    print(f"=== #{number} {title} ===")
   200|    print(url)
   201|    print()
   202|
   203|    # Build a flat timeline: merge top-level comments and their replies, sorted by time.
   204|    # Each entry: (datetime, short_id, author, body, reply_to_short_or_None, reply_to_author_or_None)
   205|    events = []
   206|    top_level_map = {}  # node_id -> short_id
   207|
   208|    short_id = 0
   209|    for c in comments:
   210|        short_id += 1
   211|        sid = short_id
   212|        top_level_map[c["id"]] = sid
   213|        events.append({
   214|            "time": c["createdAt"],
   215|            "short_id": sid,
   216|            "author": c["author"]["login"] if c["author"] else "ghost",
   217|            "body": c["body"],
   218|            "reply_to": None,
   219|            "reply_to_author": None,
   220|        })
   221|
   222|        for r in c["replies"]["nodes"]:
   223|            short_id += 1
   224|            reply_parent = c["id"]  # replies are always to the top-level comment
   225|            events.append({
   226|                "time": r["createdAt"],
   227|                "short_id": short_id,
   228|                "author": r["author"]["login"] if r["author"] else "ghost",
   229|                "body": r["body"],
   230|                "reply_to": reply_parent,
   231|                "reply_to_author": c["author"]["login"] if c["author"] else "ghost",
   232|            })
   233|
   234|    # Sort by time
   235|    events.sort(key=lambda e: e["time"])
   236|
   237|    # Build short_id -> (author, body_preview) mapping
   238|    short_id_to_meta = {}
   239|    short_id_to_node = {}
   240|    for c in comments:
   241|        sid = top_level_map[c["id"]]
   242|        short_id_to_meta[sid] = (c["author"]["login"] if c["author"] else "ghost", c["body"])
   243|        short_id_to_node[sid] = c["id"]
   244|        for r in c["replies"]["nodes"]:
   245|            # Find short_id for this reply
   246|            for ev in events:
   247|                if ev["body"] == r["body"] and ev["author"] == (r["author"]["login"] if r["author"] else "ghost"):
   248|                    sid_r = ev["short_id"]
   249|                    short_id_to_meta[sid_r] = (ev["author"], r["body"])
   250|                    short_id_to_node[sid_r] = r["id"]
   251|                    break
   252|
   253|    # Print events
   254|    for ev in events:
   255|        print(f"[{ev['short_id']}] @{ev['author']} · {format_time(ev['time'])}")
   256|        if ev["reply_to"]:
   257|            parent_sid = top_level_map.get(ev["reply_to"])
   258|            if parent_sid:
   259|                print(f"  \u21b3 回复 [{parent_sid}]")
   260|            else:
   261|                print(f"  \u21b3 回复 @{ev['reply_to_author']}")
   262|        print(ev["body"])
   263|        print()
   264|
   265|    # Save state
   266|    state = load_state()
   267|    disc_key = str(number)
   268|    if disc_key not in state["discussions"]:
   269|        state["discussions"][disc_key] = {}
   270|    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
   271|    state["discussions"][disc_key]["last_read_at"] = now
   272|    state["discussions"][disc_key]["short_ids"] = {str(k): v for k, v in short_id_to_node.items()}
   273|    state["discussions"][disc_key]["short_id_meta"] = {
   274|        str(k): {"author": v[0], "body_preview": body_preview(v[1])}
   275|        for k, v in short_id_to_meta.items()
   276|    }
   277|    save_state(state)
   278|
   279|# ── Command: post ───────────────────────────────────────────────────────────
   280|
   281|def cmd_post(token, number, body, reply_to=None):
   282|    # First get discussion ID
   283|    query = """
   284|    query($number: Int!) {
   285|      repository(owner: "%s", name: "%s") {
   286|        discussion(number: $number) {
   287|          id
   288|        }
   289|      }
   290|    }
   291|    """ % (REPO_OWNER, REPO_NAME)
   292|
   293|    data = gql(query, variables={"number": number}, token=token)
   294|    discussion = data["repository"]["discussion"]
   295|    if not discussion:
   296|        print(f"error: discussion #{number} not found", file=sys.stderr)
   297|        sys.exit(EXIT_GRAPHQL)
   298|
   299|    discussion_id = discussion["id"]
   300|
   301|    if reply_to is not None:
   302|        # Look up node ID from state
   303|        state = load_state()
   304|        short_ids = state.get("discussions", {}).get(str(number), {}).get("short_ids", {})
   305|        node_id = short_ids.get(str(reply_to))
   306|        if not node_id:
   307|            print(f"error: short id [{reply_to}] not found. run 'teahouse read {number}' first.", file=sys.stderr)
   308|            sys.exit(EXIT_SHORT_ID)
   309|
   310|        mutation = """
   311|        mutation($discussionId: ID!, $body: String!, $replyToId: ID!) {
   312|          addDiscussionComment(input: {discussionId: $discussionId, body: $body, replyToId: $replyToId}) {
   313|            comment { id url }
   314|          }
   315|        }
   316|        """
   317|        variables = {"discussionId": discussion_id, "body": body, "replyToId": node_id}
   318|    else:
   319|        mutation = """
   320|        mutation($discussionId: ID!, $body: String!) {
   321|          addDiscussionComment(input: {discussionId: $discussionId, body: $body}) {
   322|            comment { id url }
   323|          }
   324|        }
   325|        """
   326|        variables = {"discussionId": discussion_id, "body": body}
   327|
   328|    data = gql(mutation, variables=variables, token=token)
   329|    comment = data["addDiscussionComment"]["comment"]
   330|    print(f"posted: {comment['url']}")
   331|
   332|# ── Command: delete ─────────────────────────────────────────────────────────
   333|
   334|def cmd_delete(token, number, short_id, yes=False):
   335|    state = load_state()
   336|    disc_state = state.get("discussions", {}).get(str(number), {})
   337|    node_id = disc_state.get("short_ids", {}).get(str(short_id))
   338|
   339|    if not node_id:
   340|        print(f"error: short id [{short_id}] not found. run 'teahouse read {number}' first.", file=sys.stderr)
   341|        sys.exit(EXIT_SHORT_ID)
   342|
   343|    if not yes:
   344|        meta = disc_state.get("short_id_meta", {}).get(str(short_id), {})
   345|        author = meta.get("author", "?")
   346|        preview = meta.get("body_preview", "")
   347|        resp = input(f'delete comment [{short_id}] by @{author}: "{preview}"? [y/N] ')
   348|        if resp.strip().lower() != "y":
   349|            print("aborted.")
   350|            return
   351|
   352|    mutation = """
   353|    mutation($id: ID!) {
   354|      deleteDiscussionComment(input: {id: $id}) {
   355|        comment { id }
   356|      }
   357|    }
   358|    """
   359|    gql(mutation, variables={"id": node_id}, token=token)
   360|    print(f"deleted: comment [{short_id}] from discussion #{number}")
   361|
   362|    # Clean up state
   363|    disc_state["short_ids"].pop(str(short_id), None)
   364|    disc_state["short_id_meta"].pop(str(short_id), None)
   365|    save_state(state)
   366|
   367|# ── Main ────────────────────────────────────────────────────────────────────
   368|
   369|def print_usage():
   370|    print("""teahouse - GitHub Discussions CLI
   371|
   372|Usage:
   373|  teahouse list
   374|  teahouse read <number> [--limit N]
   375|  teahouse post <number> "<body>" [--reply-to <short_id>]
   376|  teahouse delete <discussion_number> <short_id> [-y]
   377|
   378|Environment:
   379|  GITHUB_TOKEN    GitHub personal access token (required)""")
   380|
   381|def main():
   382|    if len(sys.argv) < 2:
   383|        print_usage()
   384|        sys.exit(1)
   385|
   386|    command = sys.argv[1]
   387|
   388|    if command in ("-h", "--help"):
   389|        print_usage()
   390|        sys.exit(0)
   391|
   392|    # Get token
   393|    token = os.environ.get("GITHUB_TOKEN")
   394|    if not token:
   395|        print("error: GITHUB_TOKEN not set", file=sys.stderr)
   396|        sys.exit(EXIT_NO_TOKEN)
   397|
   398|    if command == "list":
   399|        cmd_list(token)
   400|
   401|    elif command == "read":
   402|        if len(sys.argv) < 3:
   403|            print("error: teahouse read <number> [--limit N]", file=sys.stderr)
   404|            sys.exit(1)
   405|        number = int(sys.argv[2])
   406|        limit = 20
   407|        if "--limit" in sys.argv:
   408|            idx = sys.argv.index("--limit")
   409|            limit = int(sys.argv[idx + 1])
   410|        cmd_read(token, number, limit)
   411|
   412|    elif command == "post":
   413|        if len(sys.argv) < 4:
   414|            print('error: teahouse post <number> "<body>" [--reply-to N]', file=sys.stderr)
   415|            sys.exit(1)
   416|        number = int(sys.argv[2])
   417|        body = sys.argv[3]
   418|        reply_to = None
   419|        if "--reply-to" in sys.argv:
   420|            idx = sys.argv.index("--reply-to")
   421|            reply_to = int(sys.argv[idx + 1])
   422|        cmd_post(token, number, body, reply_to)
   423|
   424|    elif command == "delete":
   425|        if len(sys.argv) < 4:
   426|            print("error: teahouse delete <discussion_number> <short_id> [-y]", file=sys.stderr)
   427|            sys.exit(1)
   428|        number = int(sys.argv[2])
   429|        short_id = int(sys.argv[3])
   430|        yes = "-y" in sys.argv or "--yes" in sys.argv
   431|        cmd_delete(token, number, short_id, yes)
   432|
   433|    else:
   434|        print(f"error: unknown command '{command}'", file=sys.stderr)
   435|        print_usage()
   436|        sys.exit(1)
   437|
   438|if __name__ == "__main__":
   439|    main()
   440|