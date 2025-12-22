/* =========================
   Chat Quiz Engine v2 (patched)
   - 選項卡在右側（user）
   - 修正 Q1 renderChoices / options 不一致
   - msg class 改成 ai/user
   - user avatar 放右側
   ========================= */

(function () {
  const cfg = window.__QUIZ_CONFIG__;
  if (!cfg) return;

  const chatBody = document.getElementById("chatBody");
  const progressText = document.getElementById("progressText");
  const freeTextInput = document.getElementById("freeText");
  const sendFreeTextBtn = document.getElementById("sendFreeText");

  const quizId = cfg.quiz_id;
  const total = cfg.total;

  // answers[qid] = { choice: "A. ...", multi: ["A. ..."], free_text: "..." }
  const answers = {};

  let idx = 0; // current question index
  let submitting = false;

  // ====== 題庫 ======
  const INSURANCE_QUESTIONS = [
    {
      id: "Q1",
      text: "Q1. 這份保險主要是要幫誰規劃？",
      renderChoices: [
        { key: "A", text: "我自己" },
        { key: "B", text: "配偶 / 伴侶" },
        { key: "C", text: "小孩" },
        { key: "D", text: "父母 / 長輩" },
        { key: "E", text: "公司員工（一群人）" }
      ],
      multi: false
    },
    {
      id: "Q2",
      text: "Q2. 被保險人的年齡大約是？",
      options: [
        { key: "A", text: "0–20" },
        { key: "B", text: "21–30" },
        { key: "C", text: "31–45" },
        { key: "D", text: "46–60" },
        { key: "E", text: "61 以上" }
      ],
      multi: false
    },
    {
      id: "Q3",
      text: "Q3. 目前的身分？",
      options: [
        { key: "A", text: "學生" },
        { key: "B", text: "上班族" },
        { key: "C", text: "自營 / 兼職 / 高風險工作" },
        { key: "D", text: "家庭主婦 / 夫" },
        { key: "E", text: "退休" }
      ],
      multi: false
    },
    {
      id: "Q4",
      text: "Q4. 家庭狀況？",
      options: [
        { key: "A", text: "單身" },
        { key: "B", text: "已婚，沒有小孩" },
        { key: "C", text: "已婚，有小孩" },
        { key: "D", text: "需要照顧長輩" }
      ],
      multi: false
    },
    {
      id: "Q5",
      text: "Q5. 你現在最擔心哪些事情？（可複選）",
      options: [
        { key: "A", text: "生病住院、手術費太高" },
        { key: "B", text: "得到癌症或重大疾病" },
        { key: "C", text: "將來失能或需要人長期照顧" },
        { key: "D", text: "若我意外或身故，家人生活怎麼辦" },
        { key: "E", text: "常騎車/開車，擔心意外骨折、車禍" },
        { key: "F", text: "為退休/子女教育準備一筆錢（穩穩存、穩穩領）" },
        { key: "G", text: "想要有投資報酬，可接受有漲有跌" },
        { key: "H", text: "希望定期健檢、線上健康管理" },
        { key: "I", text: "我是老闆/管理者，想幫員工規劃保障" }
      ],
      multi: true
    },
    {
      id: "Q6",
      text: "Q6. 你最在意保障的「時間長度」？",
      options: [
        { key: "A", text: "短期 1–3 年，先解決眼前需求" },
        { key: "B", text: "10–20 年，中長期規劃" },
        { key: "C", text: "希望保障到老，甚至終身" }
      ],
      multi: false
    },
    {
      id: "Q7",
      text: "Q7. 對投資風險的接受度？",
      options: [
        { key: "A", text: "很保守，只想穩定存錢" },
        { key: "B", text: "可接受有漲有跌，但不要太刺激" },
        { key: "C", text: "可接受較大波動，長期有機會成長" }
      ],
      multi: false
    },
    {
      id: "Q8",
      text: "Q8. 你比較希望透過什麼方式投保？",
      options: [
        { key: "A", text: "用手機/電腦自己線上完成" },
        { key: "B", text: "去銀行辦理（定存/基金時順便問）" },
        { key: "C", text: "透過業務或行銷人員面談" }
      ],
      multi: false
    },
    {
      id: "Q9",
      text: "Q9. 未來 1 年內，你是否有如下計畫？（可複選）",
      options: [
        { key: "A", text: "海外旅遊、出差" },
        { key: "B", text: "國內環島、登山、潛水等活動" },
        { key: "C", text: "公司打算幫員工規劃團體保險" }
      ],
      multi: true
    }
  ];

  const VALUES_QUESTIONS = [
    { id: "V1", text: "Q1. 你的年齡區間？", options: [
      {key:"A", text:"18 以下"}, {key:"B", text:"19–25"}, {key:"C", text:"26–35"},
      {key:"D", text:"36–45"}, {key:"E", text:"46 以上"}
    ], multi:false },
    { id: "V2", text: "Q2. 你的性別？", options: [
      {key:"A", text:"男"}, {key:"B", text:"女"}, {key:"C", text:"不便透露"}
    ], multi:false },
    { id: "V3", text: "Q3. 你的職業類型？", options: [
      {key:"A", text:"學生"}, {key:"B", text:"上班族"}, {key:"C", text:"自營/自由業"},
      {key:"D", text:"家庭照顧者"}, {key:"E", text:"退休/其他"}
    ], multi:false },
    { id: "V4", text: "Q4. 面對風險你比較偏向？", options: [
      {key:"A", text:"能避就避，穩定最重要"},
      {key:"B", text:"可以承擔一些風險換取更好結果"},
      {key:"C", text:"願意承擔較大風險追求成長"}
    ], multi:false },
    { id: "V5", text: "Q5. 你更重視？", options: [
      {key:"A", text:"當下生活品質"},
      {key:"B", text:"長期累積與未來保障"},
      {key:"C", text:"兩者都要平衡"}
    ], multi:false },
    { id: "V6", text: "Q6. 你對「家庭責任」的感受？", options: [
      {key:"A", text:"我需要扛起主要責任"},
      {key:"B", text:"有責任但可分擔"},
      {key:"C", text:"目前責任較少/不明顯"}
    ], multi:false },
    { id: "V7", text: "Q7. 你更在意保障的是？", options: [
      {key:"A", text:"醫療/住院/手術"},
      {key:"B", text:"重大傷病/癌症"},
      {key:"C", text:"意外/失能"},
      {key:"D", text:"退休/年金/財務規劃"}
    ], multi:false },
    { id: "V8", text: "Q8. 你做決策通常？", options: [
      {key:"A", text:"很快決定，先做再說"},
      {key:"B", text:"會做功課比較後再決定"},
      {key:"C", text:"需要別人建議/一起討論"}
    ], multi:false },
    { id: "V9", text: "Q9. 你對保險的期待更像？", options: [
      {key:"A", text:"最基本先有，不求複雜"},
      {key:"B", text:"想要完整配置，避免風險缺口"},
      {key:"C", text:"想要有彈性/可調整"}
    ], multi:false },
    { id: "V10", text: "Q10. 你對保費支出的態度？", options: [
      {key:"A", text:"越低越好，能省則省"},
      {key:"B", text:"合理就好，重點是保障到位"},
      {key:"C", text:"願意付更多換更安心/更好的服務"}
    ], multi:false },
    { id: "V11", text: "Q11. 你對「長期照顧」的擔心程度？", options: [
      {key:"A", text:"不太擔心"},
      {key:"B", text:"有點擔心"},
      {key:"C", text:"非常擔心/家族有案例"}
    ], multi:false },
    { id: "V12", text: "Q12. 最終動機：你希望透過保險解決什麼？（可選也可輸入）", options: [
      {key:"A", text:"讓家人更安心"},
      {key:"B", text:"降低突發醫療支出風險"},
      {key:"C", text:"長期財務規劃/退休"},
      {key:"D", text:"把風險轉嫁，生活更穩"}
    ], multi:false }
  ];

  function getQuestions() {
    return quizId === "insurance" ? INSURANCE_QUESTIONS : VALUES_QUESTIONS;
  }
  const QUESTIONS = getQuestions();

  // ====== UI helper ======
  function injectSelectedStyle() {
    const style = document.createElement("style");
    style.textContent = `
      .opt-btn.is-selected{
        border-color: rgba(43,89,255,.55) !important;
        box-shadow: 0 14px 26px rgba(43,89,255,.14) !important;
        transform: translateY(-1px);
      }
      .qa-actions{ display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }
    `;
    document.head.appendChild(style);
  }

  function scrollToBottom() {
    chatBody.scrollTop = chatBody.scrollHeight;
  }

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function addMsg(role, text) {
    const row = el("div", role === "user" ? "msg user" : "msg ai");

    const avatar = el("div", "avatar", role === "user" ? "你" : "AI");
    const bubble = el("div", "bubble");
    bubble.textContent = text;
    if (role === "user") {
      row.appendChild(bubble);
      row.appendChild(avatar);
    } else {
      row.appendChild(avatar);
      row.appendChild(bubble);
    }
    chatBody.appendChild(row);
  }



  function optionLabel(opt) {
    return `${opt.key}. ${opt.text}`;
  }

  function ensureSlot(qid) {
    if (!answers[qid]) answers[qid] = { choice: null, multi: [], free_text: "" };
    answers[qid].choice = answers[qid].choice || null;
    answers[qid].multi = Array.isArray(answers[qid].multi) ? answers[qid].multi : [];
    answers[qid].free_text = answers[qid].free_text || "";
  }

  function setProgress() {
    const done = Math.min(idx, QUESTIONS.length);
    if (progressText) progressText.textContent = `進度：${done} / ${total}`;
  }

  // ====== 上一題按鈕（上方） ======
  function ensureTopBackButton() {
    const head = document.querySelector(".chat-head");
    if (!head) return;

    if (document.getElementById("topBackBtn")) return;

    const btn = document.createElement("button");
    btn.id = "topBackBtn";
    btn.className = "btn secondary";
    btn.textContent = "上一題";
    btn.style.padding = "10px 12px";
    btn.addEventListener("click", goPrev);

    head.appendChild(btn);
  }

  // ✅ 統一取 options：支援 options / renderChoices
  function getOptionList(q) {
    if (Array.isArray(q.options) && q.options.length) return q.options;
    if (Array.isArray(q.renderChoices) && q.renderChoices.length) return q.renderChoices;
    return [];
  }

  // ====== Render：重畫整段對話，只留當前題可互動 ======
  function render() {
    chatBody.innerHTML = "";

    addMsg("ai", `歡迎進行「${cfg.title}」。我們會以對話方式一題一題完成。`);

    // 已完成題目（0..idx-1）
    for (let i = 0; i < idx; i++) {
      const q = QUESTIONS[i];
      ensureSlot(q.id);

      addMsg("ai", q.text);

      const a = answers[q.id];
      if (q.multi) {
        const list = (a.multi || []);
        const ansText = list.length ? list.join("、") : "（未作答）";
        addMsg("user", ansText);
      } else {
        addMsg("user", a.choice ? a.choice : "（未作答）");
      }

      if (a.free_text && a.free_text.trim()) {
        addMsg("user", `（補充）${a.free_text}`);
      }
    }

    // 當前題目
    if (idx >= QUESTIONS.length) {
      addMsg("ai", "已完成問卷，正在送出並生成分析結果…");
      scrollToBottom();
      finish();
      return;
    }

    const q = QUESTIONS[idx];
    ensureSlot(q.id);

    addMsg("ai", q.text);

    // ====== ✅ 選項卡改到右側（user） ======
    const choiceSide = window.__CHOICE_SIDE__ || "right"; // "left" | "right"
    const row = el("div", `msg choice ${choiceSide}`);
    const bubble = el("div", "bubble choice-card"); // 你 CSS 若有 choice-card 會更漂亮
    const avatar = el("div", "avatar", "你");

    const title = el("div", "", "請選擇：");
    title.style.fontWeight = "900";
    title.style.marginBottom = "8px";
    bubble.appendChild(title);

    const optRow = el("div", "option-row");

    const optList = getOptionList(q);
    optList.forEach(opt => {
      const label = optionLabel(opt);
      const btn = el("button", "opt-btn", label);

      // 初始選取樣式
      if (q.multi) {
        if ((answers[q.id].multi || []).includes(label)) btn.classList.add("is-selected");
      } else {
        if (answers[q.id].choice === label) btn.classList.add("is-selected");
      }

      btn.addEventListener("click", () => {
        if (q.multi) {
          toggleMulti(q.id, label, btn);
        } else {
          setSingle(q.id, label, optRow);
        }
      });

      optRow.appendChild(btn);
    });

    bubble.appendChild(optRow);

    const hint = el(
      "div",
      "note",
      q.multi
        ? "此題可複選：點選多個，再按「下一題」確認。"
        : "此題為單選：點選一個，再按「下一題」確認。"
    );
    hint.style.marginTop = "10px";
    bubble.appendChild(hint);

    // actions（上一題/下一題）
    const actions = el("div", "qa-actions");
    const prevBtn = el("button", "btn secondary", "上一題");
    const nextBtn = el("button", "btn", idx === QUESTIONS.length - 1 ? "送出結果" : "下一題");

    prevBtn.addEventListener("click", goPrev);
    nextBtn.addEventListener("click", () => goNext(q));

    if (idx === 0) prevBtn.disabled = true;

    actions.appendChild(prevBtn);
    actions.appendChild(nextBtn);
    bubble.appendChild(actions);

    // user：bubble 在左、avatar 在右（更像聊天）
    // ✅ 統一 DOM 順序：先 avatar 再 bubble（交給 CSS 做左右對齊）
    row.appendChild(avatar);
    row.appendChild(bubble);
    chatBody.appendChild(row);


    setProgress();
    scrollToBottom();

    const topBack = document.getElementById("topBackBtn");
    if (topBack) topBack.disabled = (idx === 0);
  }

  function toggleMulti(qid, label, btn) {
    ensureSlot(qid);
    const list = answers[qid].multi;
    const pos = list.indexOf(label);
    if (pos >= 0) {
      list.splice(pos, 1);
      btn.classList.remove("is-selected");
    } else {
      list.push(label);
      btn.classList.add("is-selected");
    }
  }

  function setSingle(qid, label, optRow) {
    ensureSlot(qid);
    answers[qid].choice = label;

    Array.from(optRow.querySelectorAll(".opt-btn")).forEach(b => b.classList.remove("is-selected"));
    const chosen = Array.from(optRow.querySelectorAll(".opt-btn")).find(b => b.textContent === label);
    if (chosen) chosen.classList.add("is-selected");
  }

  function goPrev() {
    if (idx <= 0) return;
    idx -= 1;
    render();
  }

  function goNext(q) {
    const qid = q.id;
    ensureSlot(qid);

    if (q.multi) {
      const list = answers[qid].multi || [];
      const ok = list.length > 0 || (answers[qid].free_text && answers[qid].free_text.trim());
      if (!ok) {
        addMsg("ai", "此題尚未選擇任何選項；你也可以輸入補充文字，再按下一題。");
        scrollToBottom();
        return;
      }
    } else {
      const ok = (answers[qid].choice && answers[qid].choice.trim()) || (answers[qid].free_text && answers[qid].free_text.trim());
      if (!ok) {
        addMsg("ai", "此題尚未選擇；你可以點選一個選項，或輸入補充文字後再按下一題。");
        scrollToBottom();
        return;
      }
    }

    idx += 1;
    render();
  }

  // ====== 自由輸入（綁定當前題目） ======
  function onSendFreeText() {
    if (idx >= QUESTIONS.length) return;
    const text = (freeTextInput.value || "").trim();
    if (!text) return;

    const q = QUESTIONS[idx];
    ensureSlot(q.id);

    if (!answers[q.id].free_text) answers[q.id].free_text = text;
    else answers[q.id].free_text += " / " + text;

    freeTextInput.value = "";
    render();
  }

  if (sendFreeTextBtn) sendFreeTextBtn.addEventListener("click", onSendFreeText);
  if (freeTextInput) {
    freeTextInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        onSendFreeText();
      }
    });
  }

  // ====== 送出 ======
  async function finish() {
    if (submitting) return;
    submitting = true;

    const payload = { quiz_id: quizId, answers: answers };

    try {
      const res = await fetch("/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (!res.ok || data.status !== "success") {
        console.error("submit error", data);
        addMsg("ai", "送出失敗，請回到首頁重試。");
        scrollToBottom();
        submitting = false;
        return;
      }

      window.location.href = `/result/${data.user_id}`;
    } catch (e) {
      console.error(e);
      addMsg("ai", "系統連線失敗，請稍後再試。");
      scrollToBottom();
      submitting = false;
    }
  }

  // ====== init ======
  injectSelectedStyle();
  ensureTopBackButton();
  setProgress();
  render();
})();
