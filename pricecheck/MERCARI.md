# Mercari step (full AND quick checks)

Both `scripts/full_update.py` and `scripts/quick_update.py` end with a `MERCARI` block. If it says
`MERCARI: none due`, skip this step. If it says `MERCARI NOW`, the run is not finished until the listed
cards are read. They are the cards whose SNKRDUNK lowest PSA10 ask is within 5% of the user's limit, the
only ones where a cheaper listing elsewhere could turn into a buy.

Same precautions as SNKRDUNK: only as part of a price check the user asked for, in the user's browser,
Mercari's own pages in hidden same-origin iframes one at a time with pauses, no fetch/XHR, nothing
scheduled. About 1 search page per card plus 1–5 item pages.

1. Get the page script with the due cards filled in (one `device_bash` call):
   `cd "$R" && python3 scripts/mercari.py --js`
2. In the browser tab, `navigate` to `https://jp.mercari.com/` (any jp.mercari.com page works), then
   paste the printed script into `javascript_tool` **verbatim**. It returns `started N cards` at once.
3. Poll until done (each call waits up to ~45 s; repeat while it says `running`):
   ```
   await (async()=>{for(let i=0;i<90&&!window.__mq.done;i++)await window.__wsleep(500);const q=window.__mq;return q.done?q.lines.join('\n'):`running ${q.i}/${q.n}`})()
   ```
4. Save and publish the lines exactly as returned (one `device_bash` call; same credential rules as
   the rest of the check):
   ```
   cd "$R" && python3 scripts/mercari.py - <<'EOF'
   <the MC/MI/ME lines>
   EOF
   ```
5. Chat message: one line per card from its output, e.g. "Mercari: Umbreon cheapest ¥62,700 incl.
   あんしん鑑定 (fixed) vs SNKRDUNK ¥68,500". Lead with any `** AT/UNDER LIMIT` or `** AUCTION ending`
   line, with the item link: those are the alerts the site also shows. A listing without あんしん鑑定
   is flagged "no あんしん鑑定": say the user has to check the cert number themselves.

What the script does: Mercari's search (for sale, cheapest first, from half the limit up), titles that
say PSA10 for this card number (other grades/graders, lots, "PSA10 candidates" and accessories are
excluded), then the item pages of the cheapest matches for the real price, auction end time, the
あんしん鑑定 option and fee, the listing's grade field and the card number in its description. Price on
the site = listing + ¥1,700 あんしん鑑定 (free from ¥100,000). Auction prices are the current bid.
