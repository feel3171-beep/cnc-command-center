// ============================================================
// 생산관리 현황판 → Slack 자동 발송 스크립트
// 구글 스프레드시트 > 확장 프로그램 > Apps Script에 붙여넣기
// ============================================================

// ★ Slack Webhook URL을 여기에 입력하세요
const SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/여기에/웹훅URL/입력하세요";

// ★ 발송할 Slack 채널 (Webhook 기본 채널 사용 시 비워두세요)
const SLACK_CHANNEL = "";

// 시트 설정
const SHEET_NAME = "일별 현황";

// 공장별 시작 행 (시트 구조에 맞게 조정)
// 퍼플=16행, 그린/3공장/외주는 스크롤 후 확인 필요
const FACTORY_CONFIG = {
  "퍼플": { startRow: 16, color: "🟣" },
  "그린": { startRow: 27, color: "🟢" },   // ← 실제 행 번호로 수정 필요
  "3공장": { startRow: 38, color: "🏭" },  // ← 실제 행 번호로 수정 필요
  "외주": { startRow: 49, color: "📦" }     // ← 실제 행 번호로 수정 필요
};

// 각 공장 섹션 내 항목 오프셋 (시작행 기준)
const OFFSET = {
  투입인원: 1,        // startRow + 1
  총근무시간: 2,      // startRow + 2
  평균근무시간: 3,    // startRow + 3
  계획생산: 4,        // startRow + 4
  실제생산: 5,        // startRow + 5
  달성률생산: 6,      // startRow + 6
  계획포장: 7,        // startRow + 7
  실제포장: 8,        // startRow + 8
  달성률포장: 9       // startRow + 9
};

// 전체 요약 행 번호
const SUMMARY = {
  총투입인원: 6,
  총근무시간: 7,
  총계획생산: 8,
  총실제생산: 9,
  생산달성률: 10,
  총계획포장: 11,
  총실제포장: 12,
  포장달성률: 13,
  인당생산성: 14
};


/**
 * 이번 주에 해당하는 열(column) 범위를 찾는 함수
 * 헤더 행(4행)에서 날짜를 읽어 현재 주의 월~토 컬럼과 W 컬럼을 반환
 */
function findCurrentWeekColumns() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME);
  const headerRow = 4;
  const lastCol = sheet.getLastColumn();
  const headers = sheet.getRange(headerRow, 1, 1, lastCol).getValues()[0];

  const today = new Date();
  const currentYear = today.getFullYear();
  const currentMonth = today.getMonth(); // 0-indexed
  const currentDate = today.getDate();

  // 이번 주 월요일 구하기
  const dayOfWeek = today.getDay();
  const mondayOffset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek;
  const monday = new Date(today);
  monday.setDate(currentDate + mondayOffset);

  const weekDayCols = []; // 월~토 컬럼 인덱스
  let weekSummaryCol = -1; // W 컬럼 인덱스

  for (let i = 2; i < headers.length; i++) { // C열(인덱스2)부터
    const header = String(headers[i]).trim();

    // "03/09(월)" 형식 파싱
    const dateMatch = header.match(/^(\d{2})\/(\d{2})\((.)\)$/);
    if (dateMatch) {
      const month = parseInt(dateMatch[1]) - 1;
      const day = parseInt(dateMatch[2]);
      const headerDate = new Date(currentYear, month, day);

      // 이번 주에 속하는 날짜인지 확인 (월요일부터 6일간)
      const diffDays = Math.round((headerDate - monday) / (1000 * 60 * 60 * 24));
      if (diffDays >= 0 && diffDays <= 5) {
        weekDayCols.push({
          colIndex: i,
          colNum: i + 1, // 1-based
          dayName: dateMatch[3],
          dateStr: header
        });
      }
    }

    // "W1", "W2" 등 주간 합계 컬럼
    const wMatch = header.match(/^W(\d+)$/);
    if (wMatch && weekDayCols.length > 0 && weekSummaryCol === -1) {
      // 이번 주 날짜 다음에 오는 첫 W 컬럼
      weekSummaryCol = i + 1; // 1-based
    }
  }

  return { weekDayCols, weekSummaryCol };
}


/**
 * 셀 값을 읽는 헬퍼 함수
 */
function getCellValue(sheet, row, col) {
  const value = sheet.getRange(row, col).getValue();
  if (value === "" || value === null || value === undefined || value === "-") return null;
  return value;
}

function formatNumber(val) {
  if (val === null || val === undefined || val === "-" || val === "") return "-";
  if (typeof val === "number") {
    if (Number.isInteger(val)) return val.toLocaleString("ko-KR");
    return val.toFixed(1);
  }
  return String(val);
}

function formatPercent(val) {
  if (val === null || val === undefined || val === "-" || val === "") return "-";
  if (typeof val === "number") {
    return (val * 100).toFixed(1) + "%";
  }
  return String(val);
}


/**
 * 진행률 바 생성
 */
function makeProgressBar(ratio, length) {
  length = length || 20;
  if (ratio === null || isNaN(ratio)) return "░".repeat(length) + " -";
  const filled = Math.round(Math.min(ratio, 1) * length);
  const empty = length - filled;
  const pct = (ratio * 100).toFixed(1);
  return "█".repeat(filled) + "░".repeat(empty) + " " + pct + "%";
}


/**
 * Slack 메시지 생성
 */
function buildSlackMessage() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME);
  const { weekDayCols, weekSummaryCol } = findCurrentWeekColumns();

  if (weekDayCols.length === 0) {
    return "⚠️ 이번 주 데이터를 찾을 수 없습니다.";
  }

  const today = new Date();
  const dateStr = Utilities.formatDate(today, "Asia/Seoul", "M/d (E)");
  const weekNum = weekSummaryCol > 0 ?
    sheet.getRange(4, weekSummaryCol).getValue() : "";

  // ─── 헤더 ───
  let msg = "";
  msg += `📊 *[${dateStr}] 주간 생산 현황 리포트*\n`;
  msg += `━━━━━━━━━━━━━━━━━━━━━━━━━\n\n`;

  // ─── 1. 이번주 생산계획 (공장별) ───
  msg += `*▶ 이번주 생산계획*\n`;
  for (const [name, config] of Object.entries(FACTORY_CONFIG)) {
    const planRow = config.startRow + OFFSET.계획생산;
    let weeklyPlan = 0;
    if (weekSummaryCol > 0) {
      weeklyPlan = getCellValue(sheet, planRow, weekSummaryCol) || 0;
    } else {
      // W 컬럼이 없으면 일별 합산
      weekDayCols.forEach(d => {
        weeklyPlan += (getCellValue(sheet, planRow, d.colNum) || 0);
      });
    }
    msg += `  ${config.color} ${name}: ${formatNumber(weeklyPlan)}`;
    if (name !== "외주") msg += "  |";
    msg += "\n" ;
  }

  // 전체 계획 합계
  let totalPlan = 0;
  if (weekSummaryCol > 0) {
    totalPlan = getCellValue(sheet, SUMMARY.총계획생산, weekSummaryCol) || 0;
  }
  msg += `  📋 *전체 계획: ${formatNumber(totalPlan)}*\n\n`;

  // ─── 2. 일별 생산량 ───
  msg += `*▶ 일별 생산량 (실제)*\n`;
  msg += `\`\`\`\n`;
  msg += `날짜     | 퍼플    | 그린    | 3공장   | 외주    | 합계\n`;
  msg += `---------|---------|---------|---------|---------|--------\n`;

  weekDayCols.forEach(d => {
    let rowData = [];
    let dailyTotal = 0;
    for (const [name, config] of Object.entries(FACTORY_CONFIG)) {
      const val = getCellValue(sheet, config.startRow + OFFSET.실제생산, d.colNum) || 0;
      rowData.push(formatNumber(val).padStart(7));
      dailyTotal += (typeof val === "number" ? val : 0);
    }
    const totalVal = getCellValue(sheet, SUMMARY.총실제생산, d.colNum) || dailyTotal;
    msg += `${d.dateStr.padEnd(9)}|${rowData.join(" |")} |${formatNumber(totalVal).padStart(7)}\n`;
  });
  msg += `\`\`\`\n\n`;

  // ─── 3. 이번주 누적 생산량 ───
  msg += `*▶ 이번주 누적 생산량*\n`;
  let totalActual = 0;
  if (weekSummaryCol > 0) {
    totalActual = getCellValue(sheet, SUMMARY.총실제생산, weekSummaryCol) || 0;
  } else {
    weekDayCols.forEach(d => {
      totalActual += (getCellValue(sheet, SUMMARY.총실제생산, d.colNum) || 0);
    });
  }
  const achieveRate = totalPlan > 0 ? totalActual / totalPlan : 0;
  msg += `  ${formatNumber(totalActual)} / ${formatNumber(totalPlan)}\n`;
  msg += `  ${makeProgressBar(achieveRate)}\n\n`;

  // 공장별 누적
  for (const [name, config] of Object.entries(FACTORY_CONFIG)) {
    let factoryActual = 0;
    let factoryPlan = 0;
    if (weekSummaryCol > 0) {
      factoryActual = getCellValue(sheet, config.startRow + OFFSET.실제생산, weekSummaryCol) || 0;
      factoryPlan = getCellValue(sheet, config.startRow + OFFSET.계획생산, weekSummaryCol) || 0;
    } else {
      weekDayCols.forEach(d => {
        factoryActual += (getCellValue(sheet, config.startRow + OFFSET.실제생산, d.colNum) || 0);
        factoryPlan += (getCellValue(sheet, config.startRow + OFFSET.계획생산, d.colNum) || 0);
      });
    }
    const fRate = factoryPlan > 0 ? factoryActual / factoryPlan : 0;
    msg += `  ${config.color} ${name}: ${formatNumber(factoryActual)}/${formatNumber(factoryPlan)} (${formatPercent(fRate)})\n`;
  }
  msg += `\n`;

  // ─── 4. 투입인원 & 평균 근무시간 ───
  msg += `*▶ 투입인원 & 근무시간*\n`;
  msg += `\`\`\`\n`;
  msg += `날짜     | 투입인원 | 평균근무(h)\n`;
  msg += `---------|----------|----------\n`;

  weekDayCols.forEach(d => {
    const headcount = getCellValue(sheet, SUMMARY.총투입인원, d.colNum) || 0;
    const hours = getCellValue(sheet, SUMMARY.총근무시간, d.colNum) || 0;
    const avgHours = headcount > 0 ? hours / headcount : 0;
    msg += `${d.dateStr.padEnd(9)}| ${formatNumber(headcount).padStart(7)}  | ${formatNumber(avgHours).padStart(8)}\n`;
  });
  msg += `\`\`\`\n\n`;

  // 주간 평균
  let totalHeadcount = 0;
  let totalHours = 0;
  let dayCount = 0;
  weekDayCols.forEach(d => {
    const hc = getCellValue(sheet, SUMMARY.총투입인원, d.colNum);
    const hr = getCellValue(sheet, SUMMARY.총근무시간, d.colNum);
    if (hc !== null && hc > 0) {
      totalHeadcount += hc;
      totalHours += (hr || 0);
      dayCount++;
    }
  });
  const avgHeadcount = dayCount > 0 ? Math.round(totalHeadcount / dayCount) : 0;
  const avgWorkHours = totalHeadcount > 0 ? totalHours / totalHeadcount : 0;

  msg += `  👥 주간 평균 투입: *${formatNumber(avgHeadcount)}명*  |  ⏱️ 평균 근무: *${formatNumber(avgWorkHours)}h*\n\n`;

  // ─── 인당 생산성 ───
  const productivity = totalHeadcount > 0 && totalHours > 0 ? totalActual / totalHours : 0;
  msg += `  ⚡ 인당 생산성: *${formatNumber(productivity)} 개/h*\n`;
  msg += `━━━━━━━━━━━━━━━━━━━━━━━━━\n`;

  return msg;
}


/**
 * Slack으로 메시지 발송
 */
function sendToSlack() {
  const message = buildSlackMessage();

  const payload = {
    text: message,
    mrkdwn: true
  };

  if (SLACK_CHANNEL) {
    payload.channel = SLACK_CHANNEL;
  }

  const options = {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };

  const response = UrlFetchApp.fetch(SLACK_WEBHOOK_URL, options);
  const responseCode = response.getResponseCode();

  if (responseCode === 200) {
    Logger.log("✅ Slack 발송 성공!");
  } else {
    Logger.log("❌ Slack 발송 실패: " + response.getContentText());
  }

  return responseCode;
}


/**
 * 테스트용: 메시지 미리보기 (Slack 발송 없이 로그에 출력)
 */
function previewMessage() {
  const message = buildSlackMessage();
  Logger.log(message);
}


/**
 * 매일 아침 자동 발송 트리거 설정
 * ★ 최초 1회만 실행하면 됩니다
 */
function setupDailyTrigger() {
  // 기존 트리거 삭제
  const triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(trigger => {
    if (trigger.getHandlerFunction() === "sendToSlack") {
      ScriptApp.deleteTrigger(trigger);
    }
  });

  // 매일 오전 8시~9시 사이에 실행
  ScriptApp.newTrigger("sendToSlack")
    .timeBased()
    .everyDays(1)
    .atHour(8)
    .nearMinute(0)
    .create();

  Logger.log("✅ 매일 아침 8시 자동 발송 트리거가 설정되었습니다.");
}


/**
 * 메뉴 추가 (스프레드시트 열 때 자동 실행)
 */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("🚀 Slack 발송")
    .addItem("📤 지금 발송하기", "sendToSlack")
    .addItem("👀 메시지 미리보기", "previewMessage")
    .addItem("⏰ 매일 아침 자동발송 설정", "setupDailyTrigger")
    .addToUi();
}
