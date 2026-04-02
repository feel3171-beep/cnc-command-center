import pandas as pd
import sys, io, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

files = glob.glob('C:/Users/user/Downloads/*생산관리_현황판.xlsx')
path = files[0]
df = pd.read_excel(path, skiprows=1)
cols = ['작업일자','사업장','생산지시','자재코드','자재명','라인코드','라인명','라인유형','계획수량','생산수량','양품수량','불량수량','인시율','작업시간','인원','인원보정']
df.columns = cols

print('사업장:', df['사업장'].unique())
print('라인유형:', df['라인유형'].unique())
print('기간:', df['작업일자'].min(), '~', df['작업일자'].max())
print('총건수:', len(df))
print()
print('=== 사업장별 건수/생산수량 ===')
print(df.groupby('사업장').agg(건수=('생산수량','count'), 생산수량=('생산수량','sum')))
print()
print('=== 라인유형별 ===')
print(df.groupby('라인유형').agg(건수=('생산수량','count'), 생산수량=('생산수량','sum')))
print()
df['작업일자'] = pd.to_datetime(df['작업일자'])
mar = df[df['작업일자'].dt.month == 3]
print('=== 3월 사업장별 ===')
print(mar.groupby('사업장').agg(건수=('생산수량','count'), 생산수량=('생산수량','sum')))
print()
print('=== 3월 사업장-라인유형별 ===')
print(mar.groupby(['사업장','라인유형']).agg(건수=('생산수량','count'), 생산수량=('생산수량','sum')))
print()

# 3월 일별 합계
print('=== 3월 일별 전체 생산수량 ===')
daily = mar.groupby(mar['작업일자'].dt.day).agg(건수=('생산수량','count'), 생산수량=('생산수량','sum'))
print(daily)

# 생산지시 번호 샘플
print()
print('=== 생산지시 샘플 ===')
print(mar['생산지시'].head(20).values)
