import pandas as pd
import sys, io, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

files = glob.glob('C:/Users/user/Downloads/*생산관리_현황판.xlsx')
df = pd.read_excel(files[0], skiprows=1)
cols = ['작업일자','사업장','생산지시','자재코드','자재명','라인코드','라인명','라인유형','계획수량','생산수량','양품수량','불량수량','인시율','작업시간','인원','인원보정']
df.columns = cols
df['작업일자'] = pd.to_datetime(df['작업일자'])

# 사업장 -> FACTORY_CODE 매핑 확인
# 3공장=1300, 그린카운티=?, 퍼플카운티=?
# DB: 1100, 1200, 1300
# 10007277 -> FACTORY_CODE=1300, 엑셀에서 확인
sample = df[df['생산지시'] == 10007277]
print('10007277 사업장:', sample['사업장'].values)  # 3공장 -> 1300

sample2 = df[df['생산지시'] == 10008558]
print('10008558 사업장:', sample2['사업장'].values)

# 그린/퍼플 샘플 가져오기
green_orders = df[df['사업장'] == '그린카운티']['생산지시'].head(5).values
purple_orders = df[df['사업장'] == '퍼플카운티']['생산지시'].head(5).values
print('그린카운티 생산지시 샘플:', green_orders)
print('퍼플카운티 생산지시 샘플:', purple_orders)

# 3월 일별 비교용 - 사업장별-라인유형별 일별
mar = df[df['작업일자'].dt.month == 3]
print()
print('=== 3월 일별 사업장별 생산수량 ===')
pivot = mar.pivot_table(values='생산수량', index=mar['작업일자'].dt.day, columns='사업장', aggfunc='sum', fill_value=0)
print(pivot)
print()
print('=== 3월 일별 라인유형별 생산수량 ===')
pivot2 = mar.pivot_table(values='생산수량', index=mar['작업일자'].dt.day, columns='라인유형', aggfunc='sum', fill_value=0)
print(pivot2)

# 엑셀 3월26일 데이터 상세
print()
print('=== 엑셀 3/26 건수/수량 ===')
d26 = mar[mar['작업일자'].dt.day == 26]
print('총건수:', len(d26), '총생산수량:', d26['생산수량'].sum())
print(d26.groupby('사업장').agg(건수=('생산수량','count'), 생산수량=('생산수량','sum')))
