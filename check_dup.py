import pandas as pd
import sys, io, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

files = glob.glob('C:/Users/user/Downloads/*생산관리_현황판.xlsx')
df = pd.read_excel(files[0], skiprows=1)
cols = ['작업일자','사업장','생산지시','자재코드','자재명','라인코드','라인명','라인유형','계획수량','생산수량','양품수량','불량수량','인시율','작업시간','인원','인원보정']
df.columns = cols
df['작업일자'] = pd.to_datetime(df['작업일자'])

# 같은 생산지시가 여러번 나오는 케이스
dup = df.groupby('생산지시').agg(출현횟수=('작업일자','count'), 날짜수=('작업일자','nunique'), 총생산=('생산수량','sum'), 총계획=('계획수량','sum')).reset_index()
print('=== 출현횟수 분포 ===')
print(dup['출현횟수'].value_counts().sort_index().head(20))
print()

# 10007277 상세
sample = df[df['생산지시'] == 10007277].sort_values('작업일자')
print('=== ORDER 10007277 상세 ===')
print(sample[['작업일자','사업장','라인코드','라인유형','계획수량','생산수량']].to_string())
print('합계 생산수량:', sample['생산수량'].sum())
print()

# DB에서 10007277: ORD_QTY=186264, ORD_OUT_QTY=186062
print('DB: ORD_QTY=186264, ORD_OUT_QTY=186062')
