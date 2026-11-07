"""Generate assets/generated/stats.svg and langs.svg from the GitHub GraphQL API.
No third-party services: runs inside GitHub Actions with the built-in GITHUB_TOKEN."""
import json, os, sys, urllib.request, html
from datetime import date, timedelta

USER = os.environ.get("GH_USER", "kamran-nizamani")
OUT = os.environ.get("OUT_DIR", "assets/generated")

QUERY = """
query($login:String!){
  user(login:$login){
    followers{totalCount}
    repositories(ownerAffiliations:OWNER,isFork:false,first:100,privacy:PUBLIC){
      totalCount
      nodes{ stargazerCount forkCount
        languages(first:8,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}} }
    }
    contributionsCollection{
      totalCommitContributions totalPullRequestContributions totalIssueContributions
      contributionCalendar{ totalContributions weeks{contributionDays{date contributionCount}} }
    }
  }
}"""

def fetch():
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={"Authorization": "bearer " + os.environ["GITHUB_TOKEN"], "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    if "errors" in d:
        sys.exit("GraphQL error: %s" % d["errors"])
    return d["data"]["user"]

def streaks(days):
    counts = {d["date"]: d["contributionCount"] for d in days}
    today = date.today()
    cur, d = 0, today
    if counts.get(d.isoformat(), 0) == 0:  # today may not have contributions yet
        d -= timedelta(days=1)
    while counts.get(d.isoformat(), 0) > 0:
        cur += 1; d -= timedelta(days=1)
    best = run = 0
    for day in sorted(counts):
        run = run + 1 if counts[day] > 0 else 0
        best = max(best, run)
    return cur, best

def summarize(u):
    repos = u["repositories"]["nodes"]
    cc = u["contributionsCollection"]
    days = [d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    cur, best = streaks(days)
    langs = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            n = e["node"]
            l = langs.setdefault(n["name"], [0, n["color"] or "#8B949E"])
            l[0] += e["size"]
    top = sorted(langs.items(), key=lambda kv: -kv[1][0])[:6]
    total = sum(v[0] for _, v in top) or 1
    return {
        "stars": sum(r["stargazerCount"] for r in repos),
        "forks": sum(r["forkCount"] for r in repos),
        "repos": u["repositories"]["totalCount"],
        "followers": u["followers"]["totalCount"],
        "commits": cc["totalCommitContributions"],
        "prs": cc["totalPullRequestContributions"],
        "issues": cc["totalIssueContributions"],
        "year": cc["contributionCalendar"]["totalContributions"],
        "cur": cur, "best": best,
        "langs": [(n, v[0] / total * 100, v[1]) for n, v in top],
    }

STYLE = """<style>.mono{font-family:'JetBrains Mono','Fira Code',Consolas,Menlo,monospace}.sans{font-family:'Inter','Segoe UI',Helvetica,Arial,sans-serif}</style>"""

def stats_svg(s):
    tiles = [("Contributions (1y)", s["year"], "#14B8A6"), ("Commits", s["commits"], "#38BDF8"),
             ("Pull requests", s["prs"], "#A78BFA"), ("Issues", s["issues"], "#F59E0B"),
             ("Stars earned", s["stars"], "#FCD34D"), ("Public repos", s["repos"], "#5EEAD4")]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 250" width="900" height="250" role="img" aria-label="GitHub stats for {USER}">{STYLE}',
           '<rect x="0.5" y="0.5" width="899" height="249" rx="16" fill="#0D1117" stroke="#14B8A6" stroke-opacity="0.35"/>',
           f'<text class="mono" x="28" y="40" font-size="14" fill="#14B8A6">$ stats --user {USER}</text>']
    for i, (label, val, col) in enumerate(tiles):
        x = 28 + (i % 3) * 190; y = 64 + (i // 3) * 76
        out.append(f'<rect x="{x}" y="{y}" width="174" height="62" rx="12" fill="{col}" fill-opacity="0.09" stroke="{col}" stroke-opacity="0.3"/>'
                   f'<text class="sans" x="{x+14}" y="{y+34}" font-size="26" font-weight="800" fill="#FFFFFF">{val:,}</text>'
                   f'<text class="mono" x="{x+14}" y="{y+52}" font-size="11" fill="#8B949E">{html.escape(label)}</text>')
    # streak panel
    out.append('<rect x="610" y="64" width="262" height="138" rx="12" fill="#14B8A6" fill-opacity="0.09" stroke="#14B8A6" stroke-opacity="0.3"/>')
    out.append(f'<text class="mono" x="628" y="90" font-size="11" fill="#8B949E">CURRENT STREAK</text>'
               f'<text class="sans" x="628" y="128" font-size="40" font-weight="800" fill="#5EEAD4">{s["cur"]}<tspan font-size="16" fill="#8B949E"> days</tspan></text>'
               f'<text class="mono" x="628" y="160" font-size="11" fill="#8B949E">LONGEST STREAK</text>'
               f'<text class="sans" x="628" y="188" font-size="22" font-weight="700" fill="#FFFFFF">{s["best"]}<tspan font-size="13" fill="#8B949E"> days</tspan></text>')
    out.append(f'<text class="mono" x="28" y="232" font-size="11" fill="#6B7280">{s["followers"]} followers · {s["forks"]} forks · updated {date.today().isoformat()}</text></svg>')
    return "".join(out)

def langs_svg(s):
    h = 70 + len(s["langs"]) * 30 + 20
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 440 {h}" width="440" height="{h}" role="img" aria-label="Top languages">{STYLE}',
           f'<rect x="0.5" y="0.5" width="439" height="{h-1}" rx="16" fill="#0D1117" stroke="#14B8A6" stroke-opacity="0.35"/>',
           '<text class="mono" x="24" y="38" font-size="14" fill="#14B8A6">$ langs --top</text>']
    x = 24
    for n, pct, col in s["langs"]:  # stacked bar
        w = 392 * pct / 100
        out.append(f'<rect x="{x:.1f}" y="52" width="{max(w,1):.1f}" height="10" fill="{col}"/>'); x += w
    for i, (n, pct, col) in enumerate(s["langs"]):
        y = 92 + i * 30
        out.append(f'<circle cx="32" cy="{y-4}" r="6" fill="{col}"/><text class="sans" x="48" y="{y}" font-size="14" fill="#E6EDF3">{html.escape(n)}</text>'
                   f'<text class="mono" x="416" y="{y}" font-size="13" fill="#8B949E" text-anchor="end">{pct:.1f}%</text>')
    out.append("</svg>")
    return "".join(out)

def write(s):
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "stats.svg"), "w").write(stats_svg(s))
    open(os.path.join(OUT, "langs.svg"), "w").write(langs_svg(s))

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--mock":
        write({"stars": 12, "forks": 3, "repos": 24, "followers": 18, "commits": 480, "prs": 31, "issues": 9, "year": 612,
               "cur": 7, "best": 21, "langs": [("TypeScript", 38.2, "#3178c6"), ("Python", 27.5, "#3572A5"), ("JavaScript", 18.1, "#f1e05a"),
                                                ("Java", 8.4, "#b07219"), ("CSS", 4.6, "#563d7c"), ("HTML", 3.2, "#e34c26")]})
    else:
        write(summarize(fetch()))
    print("written to", OUT)
