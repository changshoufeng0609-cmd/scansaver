# ScanSaver 隊友指南(2026-07-18 狀態)

> 一句話:**跟 AI 講一次你要做什麼檢查,它幫你打電話問遍影像中心、逐項拆解現金價、
> 抓話術紅旗、拿真實報價回頭砍價,最後給你一份附錄音逐字稿的排名推薦。**
> (ElevenLabs「The Negotiator」挑戰,醫療影像垂直)

## 目前進度

| 里程碑 | 狀態 |
|---|---|
| M0 環境 / M1 建 agent / M2 語音進件 / M3 文件解析 | ✅ 完成 |
| M8 真實市場基準價(CMS/灣區現金價,ZIP 94301) | ✅ 完成 |
| M4 第一通電話驗收 | ⚠️ 功能通了,卡在測試電話音質(斷斷續續),待重測 |
| M5 三通市場輪 / M6 談判輪 / M7 報告 | ⏳ 等 M4 通過後排練 |

## 誰要做什麼

- **跑系統的人只需要一台電腦**(目前是 Shou-Feng 的:FastAPI + SQLite + ngrok +
  ElevenLabs workspace 都繫在上面)。其他人**不需要**架環境。
- **演診所櫃台的人**只需要:自己的手機 + 本文件下面的角色速查表(完整劇本在
  `agents/counterparties/*.md`,建議整份讀一遍,對話用英文)。
- **改程式碼的人**:clone 本 repo 發 PR。секrets(`.env`)不在 git 裡,跟主機的人拿。

## 操作(儀表板 = http://localhost:8000,或公開網址 https://enlisted-edition-graveness.ngrok-free.dev)

1. **01 Intake** — 跟 widget 裡的 Estimator 講需求(英文),或上傳醫囑照片。
   也可以直接打 **+1 605 566 4795**(Estimator 會接聽)。
2. **02 Confirm** — 按 Load latest 檢查 JSON,可直接編輯,按 Confirm。沒確認不會打電話。
3. **03 The calls** — 「Start a call」填 **要撥的電話**(演櫃台的隊友手機,+1 開頭)+
   **診所名**(下拉選三家之一)→ Call。報價會即時出現在 ledger,紅旗自動蓋章,
   下方有通話狀態(done/failed)。第二輪勾 **negotiate** 再打,就是砍價模式。
4. **04 The close** — Generate report:排名、省了多少、引用逐字稿、可播錄音。

重置 demo 資料:刪掉 `data/scansaver.db` 即可(自動重建空庫)。

## 三個櫃台角色速查(demo 的核心演出)

> 共通規則:對方是 AI 打來的。若你問 "Are you a robot?" 它會誠實承認——**不要掛斷**,
> 照劇本繼續。每句話講短一點,自然一點。

### 角色 1:Dana @ Summit Imaging Center(石牆型 → 產出「回電承諾」)
- 政策:電話裡不報價。先擋:「We don't give prices over the phone.」
- 對方有禮貌地堅持+講清楚檢查內容後,才鬆口區間:
  **"Self-pay it's usually somewhere in the seven hundred to nine hundred range."**
- 絕不拆項、絕不確認判讀費含不含(「that's a billing question」)、絕不談判。
- 結局固定給回電承諾:**"Best I can do is have Priya from billing call you back
  tomorrow between ten and eleven. What's the number?"**
- 中途至少一次「sorry, one second—」假裝忙線再回來。

### 角色 2:Marcus @ ValueScan Radiology(釣魚價型 → 產出紅旗)
- 開口就熱情報:**"$350 — cheapest you'll find anywhere."**
- 被「點名問到」才承認的隱藏費用:判讀費 **$180**、設施費 **$95**(真實全含 $625,
  絕不主動說)。
- 被要求書面報價就閃躲:「We don't really do email quotes, just come in.」
- 聽到競爭報價不砍價:「Nobody beats $350.」順勢推銷:「I've got a slot Thursday.」

### 角色 3:Sloane @ Premier Diagnostic Imaging(高價可談型 → 產出「當場降價」)
- 開價:**"$950, genuinely all-inclusive."** 樂意拆項:tech $600 / read $250 / facility $100。
- 推銷一次 3-Tesla 升級(+$200)和「Thursday 名額快沒了」。
- **讓價階梯,嚴格照順序,沒有籌碼絕不讓:**
  1. 對方只是喊貴 → 守住 $950,重講品質
  2. 對方問自費/預付折扣 → **$900**
  3. 對方引用具體競爭報價 $X(≥$675)→ **報 X−25**,例:對方說 $750 →
     "I can do **seven twenty-five**, all-in, same-week."
  4. 競爭報價 <$675 → 不跟,守地板:「At $675 all-in with a 24-hour read,
     we're the better buy.」**$675 是絕對地板**
- 成交前**把最終數字大聲重講一遍**(這句會進逐字稿當證據)。

## Demo 主線(預計)

1. Estimator 進件(順便讓評審看 AI 揭露:問它 are you a robot)
2. 三通市場輪:Dana(回電承諾)→ Marcus(釣魚價被拆穿+紅旗)→ Sloane($950 入帳)
3. 談判輪:勾 negotiate 再打 Sloane → 它引用真實最低價 → Sloane 讓到 ~$725 →
   儀表板出現劃線降價
4. Generate report:排名 + "saved $225 (24%)" + 播一段錄音
5. 亮點補充:config 換 `moving.example.json` = 零程式碼換垂直

## 紅線(評分標準,不可違反)

- 不打真診所。測試/demo 只打隊友的、自己的電話。
- 不捏造報價或競爭報價;談判籌碼只能來自 DB 裡真實 log 過的報價。
- Agent 被問到時必須承認自己是 AI——這是加分項,不是 bug。
