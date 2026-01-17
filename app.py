import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timedelta
import plotly.express as px  # 用于画交互式图表

# ==========================================
# 1. 核心爬虫逻辑 (保持不变，但去掉了print)
# ==========================================
class PPCrawler:
    def __init__(self, school_name, phone, password):
        self.base_url = "https://api.pp.ltd/api"
        self.school_name = school_name
        self.phone = phone
        self.password = password
        self.token = None
        self.headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
        }

    def login(self):
        login_url = f"{self.base_url}/auth/login"
        payload = {"phone": self.phone, "password": self.password, "ticket": ""}
        try:
            response = requests.post(login_url, json=payload, headers=self.headers, timeout=5)
            if response.status_code == 200:
                self.token = response.json().get("data", {}).get("token")
                if self.token:
                    self.headers["Authorization"] = f"Bearer {self.token}"
                    return True
        except:
            pass
        return False

    def fetch_teacher_stats(self, start_date_str, end_date_str):
        stats_url = f"{self.base_url}/administratorTable/taskList" 
        all_results = []
        page = 1
        
        # 创建一个占位符用于更新进度
        progress_text = f"正在抓取 {self.school_name} 数据..."
        
        while True:
            params = {
                "page": page, 
                "pageSize": 50, 
                "startDate": start_date_str, 
                "endDate": end_date_str
            }
            try:
                response = requests.get(stats_url, params=params, headers=self.headers, timeout=10)
                if response.status_code == 200:
                    data_json = response.json()
                    rows = data_json.get("data", {}).get("list", [])
                    if not rows: break
                    
                    all_results.extend(rows)
                    total = data_json.get("data", {}).get("total", 0)
                    
                    if len(all_results) >= total: break
                    page += 1
                else:
                    break
            except:
                break
        return all_results

# ==========================================
# 2. 数据处理函数
# ==========================================
@st.cache_data(ttl=3600) # 缓存数据1小时，防止重复点击按钮重复爬取
def get_all_data(accounts, start_date, end_date):
    mapping = {
        'name': '任务名称',
        'createdUserName': '老师',
        'subjectName': '科目',
        'gradeName': '年级',
        'createdAt': '创建时间',
        'blankCount': '批阅题空数'
    }
    
    all_school_data = pd.DataFrame()
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, acc in enumerate(accounts):
        status_text.text(f"正在连接: {acc['name']}...")
        crawler = PPCrawler(acc["name"], acc["phone"], acc["pw"])
        
        if crawler.login():
            raw_data = crawler.fetch_teacher_stats(start_date, end_date)
            if raw_data:
                df = pd.DataFrame(raw_data)
                # 列映射
                existing_cols = [c for c in mapping.keys() if c in df.columns]
                df_final = df[existing_cols].rename(columns=mapping)
                df_final['学校'] = acc['name'] # 添加学校列
                
                # 统一时间格式
                if '创建时间' in df_final.columns:
                    df_final['创建时间'] = pd.to_datetime(df_final['创建时间']).dt.strftime('%Y-%m-%d')
                    
                all_school_data = pd.concat([all_school_data, df_final], ignore_index=True)
        
        # 更新进度条
        progress_bar.progress((i + 1) / len(accounts))
    
    status_text.empty()
    progress_bar.empty()
    return all_school_data

# ==========================================
# 3. Streamlit 页面布局
# ==========================================

# 设置网页标题和图标
st.set_page_config(page_title="多校教学数据看板", page_icon="📊", layout="wide")

# 侧边栏：配置区
with st.sidebar:
    st.header("⚙️ 查询设置")
    
    # 日期选择器
    default_start = datetime.now() - timedelta(days=30)
    default_end = datetime.now()
    
    col1, col2 = st.columns(2)
    start_date = col1.date_input("开始日期", default_start)
    end_date = col2.date_input("结束日期", default_end)
    
    # 账号配置 (实际部署时建议放入 secrets 或配置文件)
    accounts = [
        {"name": "崂山实验", "phone": "15100000340", "pw": "000340"},
        {"name": "青岛实验高中", "phone": "15100000395", "pw": "000395"},
        {"name": "青岛二实验", "phone": "15100000394", "pw": "000394"},
        {"name": "杜威实验学校", "phone": "15100000191", "pw": "000191"},
        {"name": "六十七中", "phone": "15100000463", "pw": "000463"},
        {"name": "三十九中", "phone": "15100000571", "pw": "000571"},
        {"name": "十七中", "phone": "15100000497", "pw": "000497"},
    ]
    
    fetch_btn = st.button("🚀 开始查询数据", type="primary")

# 主页面
st.title("📊 多校联合教学数据看板")
st.markdown(f"**当前查询范围：** {start_date} 至 {end_date}")

if fetch_btn:
    # 转换日期为字符串
    s_str = start_date.strftime("%Y-%m-%d")
    e_str = end_date.strftime("%Y-%m-%d")
    
    with st.spinner('正在从服务器抓取最新数据，请稍候...'):
        df_all = get_all_data(accounts, s_str, e_str)
    
    if not df_all.empty:
        st.success(f"数据抓取完成！共获取 {len(df_all)} 条记录")
        
        # --- 模块1：关键指标 (KPI) ---
        st.subheader("1. 总体概览")
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("总任务数", len(df_all))
        kpi2.metric("活跃教师数", df_all['老师'].nunique())
        kpi3.metric("涉及学校", df_all['学校'].nunique())
        kpi4.metric("批阅题空总量", int(df_all['批阅题空数'].sum()))
        
        st.divider() # 分割线
        
        # --- 模块2：图表展示 ---
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.subheader("各校任务量对比")
            # 按学校汇总
            school_stats = df_all.groupby('学校').size().reset_index(name='任务数')
            fig_bar = px.bar(school_stats, x='学校', y='任务数', color='任务数', 
                             text_auto=True, title="各校任务总数")
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with col_chart2:
            st.subheader("各校活跃教师对比")
            teacher_stats = df_all.groupby('学校')['老师'].nunique().reset_index(name='人数')
            fig_line = px.line(teacher_stats, x='学校', y='人数', markers=True, 
                               title="活跃教师人数趋势")
            st.plotly_chart(fig_line, use_container_width=True)

        # 堆叠图：各校科目分布
        st.subheader("各科目教师活跃度 (分学校堆叠)")
        subject_stats = df_all.groupby(['科目', '学校'])['老师'].nunique().reset_index(name='人数')
        fig_stack = px.bar(subject_stats, x='科目', y='人数', color='学校', 
                           title="各科目投入师资力量分析", barmode='stack')
        st.plotly_chart(fig_stack, use_container_width=True)

        st.divider()

        # --- 模块3：详细数据表格 ---
        st.subheader("3. 详细数据查询")
        
        # 添加过滤器
        selected_school = st.multiselect("筛选学校", df_all['学校'].unique())
        selected_subject = st.multiselect("筛选科目", df_all['科目'].unique())
        
        df_display = df_all.copy()
        if selected_school:
            df_display = df_display[df_display['学校'].isin(selected_school)]
        if selected_subject:
            df_display = df_display[df_display['科目'].isin(selected_subject)]
            
        st.dataframe(df_display, use_container_width=True)
        
        # 下载按钮
        csv = df_display.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 下载当前表格为 Excel/CSV",
            data=csv,
            file_name=f'教学数据统计_{s_str}_{e_str}.csv',
            mime='text/csv',
        )
        
    else:
        st.warning("未查询到数据，请检查网络或账号配置。")
else:
    st.info("👈 请在左侧选择日期并点击【开始查询数据】按钮")
