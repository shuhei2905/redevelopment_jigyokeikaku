
import streamlit as st
import pandas as pd
import sqlite3
import datetime
import altair as alt

# --- データベース設定 ---
DB_NAME = 'biz_plan.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            created_at TIMESTAMP,
            total_area REAL,
            target_far REAL,
            exit_unit_price INTEGER
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS landowners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            name TEXT,
            area REAL,
            market_price INTEGER,
            offer_price INTEGER,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )
    ''')
    conn.commit()
    conn.close()

# --- データベース操作 ---
def save_project(name, total_area, target_far, exit_unit_price, df_landowners):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO projects (name, created_at, total_area, target_far, exit_unit_price)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, datetime.datetime.now(), total_area, target_far, exit_unit_price))
    project_id = c.lastrowid
    
    for _, row in df_landowners.iterrows():
        c.execute('''
            INSERT INTO landowners (project_id, name, area, market_price, offer_price)
            VALUES (?, ?, ?, ?, ?)
        ''', (project_id, row['地権者名'], row['面積'], row['相場価格'], row['提示価格']))
    
    conn.commit()
    conn.close()
    return project_id

def delete_project(project_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DELETE FROM landowners WHERE project_id = ?', (project_id,))
    c.execute('DELETE FROM projects WHERE id = ?', (project_id,))
    conn.commit()
    conn.close()

def get_all_projects():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql('SELECT * FROM projects ORDER BY created_at DESC', conn)
    conn.close()
    return df

def get_landowners_by_project(project_id):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql('SELECT * FROM landowners WHERE project_id = ?', conn, params=(project_id,))
    conn.close()
    return df

# --- アプリケーション本体 ---
def main():
    st.set_page_config(page_title="事業計画シミュレーター", layout="wide")
    init_db()

    menu = st.sidebar.radio("メニュー", ["シミュレーション実行", "保存データ一覧"])

    if menu == "シミュレーション実行":
        st.title("🏗 事業計画シミュレーター")

        # --- 1. 出口条件設定 ---
        with st.container():
            col_cond1, col_cond2, col_cond3, col_cond4 = st.columns(4)
            if 'target_far' not in st.session_state: st.session_state.target_far = 300.0
            if 'exit_unit_price' not in st.session_state: st.session_state.exit_unit_price = 100
            if 'acquisition_cost_rate' not in st.session_state: st.session_state.acquisition_cost_rate = 5.0

            far = col_cond1.number_input("従後容積(%)", value=st.session_state.target_far, step=10.0)
            exit_unit_price = col_cond2.number_input("出口一種単価(万円)", value=st.session_state.exit_unit_price, step=10)
            acquisition_cost_rate = col_cond3.number_input("物件取得経費（対土地代）(%)", value=st.session_state.acquisition_cost_rate, step=0.5)
            far_ratio = far / 100.0 if far > 0 else 1.0

        st.write("---")

        # --- 2. エクセル風編集エリア (Input) ---
        st.subheader("地権者データの入力・編集")
        st.caption("👇 表を直接編集できます。行の追加は一番下の行に入力するか、右上の「＋」を押してください。")

        if 'input_df' not in st.session_state:
            st.session_state.input_df = pd.DataFrame({
                "地権者名": pd.Series(dtype='str'),
                "面積": pd.Series(dtype='float'),
                "相場価格": pd.Series(dtype='int'),
                "提示価格": pd.Series(dtype='int')
            })

        edited_df = st.data_editor(
            st.session_state.input_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "地権者名": st.column_config.TextColumn("地権者名", required=True),
                "面積": st.column_config.NumberColumn("面積 (坪)", format="%.2f", min_value=0.0, default=0.0),
                "相場価格": st.column_config.NumberColumn("相場価格 (万円)", format="%d", min_value=0, default=0),
                "提示価格": st.column_config.NumberColumn("提示価格 (万円)", format="%d", min_value=0, default=0),
            },
            key="main_editor"
        )

        # --- 3. リアルタイム計算処理 ---
        calc_df = edited_df.copy()
        calc_df["面積"] = pd.to_numeric(calc_df["面積"], errors='coerce').fillna(0.0)
        calc_df["相場価格"] = pd.to_numeric(calc_df["相場価格"], errors='coerce').fillna(0)
        calc_df["提示価格"] = pd.to_numeric(calc_df["提示価格"], errors='coerce').fillna(0)

        # 個別計算
        calc_df["差額"] = calc_df["提示価格"] - calc_df["相場価格"]
        calc_df["坪単価"] = calc_df.apply(lambda x: x["提示価格"] / x["面積"] if x["面積"] > 0 else 0, axis=1)
        calc_df["一種単価"] = calc_df.apply(lambda x: x["坪単価"] / far_ratio if far_ratio > 0 else 0, axis=1)

        # 全体集計
        total_area_sum = calc_df["面積"].sum()
        total_offer_sum = calc_df["提示価格"].sum()
        total_market_sum = calc_df["相場価格"].sum()
        
        # 物件取得経費の計算
        acquisition_cost = total_offer_sum * acquisition_cost_rate / 100.0
        
        finish_price = total_offer_sum / total_area_sum / far_ratio if (total_area_sum > 0 and far_ratio > 0) else 0
        exit_gross = total_area_sum * far_ratio * exit_unit_price
        profit = exit_gross - total_offer_sum - acquisition_cost
        profit_margin = profit / exit_gross * 100 if exit_gross > 0 else 0

        # --- 4. 重要指標 (Metrics) ---
        st.markdown("### 📊 シミュレーション結果")
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("敷地面積合計", f"{total_area_sum:,.2f} 坪")
        m2.metric("提示価格合計", f"{total_offer_sum:,.0f} 万円")
        m3.metric("物件取得経費（対土地代）", f"{acquisition_cost:,.0f} 万円")
        m4.metric("出口グロス", f"{exit_gross:,.0f} 万円")
        m5.metric("想定利益", f"{profit:,.0f} 万円", delta=f"{profit:,.0f} 万円" if profit != 0 else None)
        m6.metric("利益率", f"{profit_margin:.2f} %", delta=f"{profit_margin:.2f} %" if profit_margin != 0 else None)

        # --- 5. グラフ描画エリア ---
        if len(calc_df) > 0 and total_area_sum > 0:
            st.write("---")
            st.subheader("📈 視覚的分析")
            
            g_col1, g_col2 = st.columns(2)
            
            with g_col1:
                st.markdown("**💰 相場価格 vs 提示価格**")
                chart_data = calc_df[["地権者名", "相場価格", "提示価格"]].melt("地権者名", var_name="種別", value_name="金額(万円)")
                chart = alt.Chart(chart_data).mark_bar().encode(
                    x=alt.X('地権者名', sort=None, axis=alt.Axis(labelAngle=0)),
                    y='金額(万円)',
                    color=alt.Color('種別', scale=alt.Scale(domain=['相場価格', '提示価格'], range=['#A9A9A9', '#FF6347'])),
                    xOffset='種別',
                    tooltip=['地権者名', '種別', '金額(万円)']
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)

            with g_col2:
                st.markdown("**🏗 事業収支の構成**")
                if profit > 0:
                    donut_data = pd.DataFrame({
                        "category": ["原価(取得費)", "想定利益"],
                        "value": [total_offer_sum, profit]
                    })
                    donut_chart = alt.Chart(donut_data).mark_arc(innerRadius=50).encode(
                        theta=alt.Theta(field="value", type="quantitative"),
                        color=alt.Color(field="category", type="nominal", scale=alt.Scale(range=['#D3D3D3', '#32CD32'])),
                        tooltip=["category", "value"]
                    ).properties(height=300)
                    st.altair_chart(donut_chart, use_container_width=True)
                else:
                    st.warning("⚠️ 現在、赤字収支です。")
                    st.bar_chart(pd.DataFrame({"金額": [exit_gross, total_offer_sum]}, index=["出口グロス", "提示価格合計"]))

            # 詳細テーブル
            with st.expander("▼ 計算詳細・内訳を見る", expanded=False):
                st.dataframe(calc_df.style.format({
                    "面積": "{:.2f}",
                    "相場価格": "{:,.0f}",
                    "提示価格": "{:,.0f}",
                    "差額": "{:,.0f}",
                    "坪単価": "{:,.2f}",
                    "一種単価": "{:,.2f}"
                }), use_container_width=True)

        # --- 6. 保存機能 ---
        st.write("---")
        c_save1, c_save2 = st.columns([3, 1])
        save_name = c_save1.text_input("プロジェクト名をつけて保存", placeholder="例：日本橋計画_Ver1")
        if c_save2.button("💾 プロジェクトを保存", type="primary"):
            if save_name and len(calc_df) > 0:
                save_project(save_name, total_area_sum, far, exit_unit_price, calc_df)
                st.success(f"「{save_name}」を保存しました！")
            elif len(calc_df) == 0:
                st.error("地権者データが入力されていません。")
            else:
                st.error("プロジェクト名を入力してください。")

    elif menu == "保存データ一覧":
        st.title("📂 保存済みプロジェクト")
        projects_df = get_all_projects()
        
        if not projects_df.empty:
            for index, project in projects_df.iterrows():
                with st.expander(f"📄 {project['name']} (作成: {project['created_at'][:16]})"):
                    c1, c2 = st.columns([4, 1])
                    landowners_df = get_landowners_by_project(project['id'])
                    
                    with c1:
                        st.caption(f"敷地: {project['total_area']:.2f}坪 | 容積: {project['target_far']}% | 出口一種: {project['exit_unit_price']}万円")
                        st.dataframe(landowners_df[["name", "area", "market_price", "offer_price"]].rename(columns={
                            "name": "地権者名", "area": "面積", "market_price": "相場価格", "offer_price": "提示価格"
                        }), hide_index=True)
                    
                    with c2:
                        if st.button("削除", key=f"del_{project['id']}"):
                            delete_project(project['id'])
                            st.rerun()
                        
                        if st.button("編集再開", key=f"load_{project['id']}"):
                            loaded_data = []
                            for _, l_row in landowners_df.iterrows():
                                loaded_data.append({
                                    "地権者名": l_row['name'],
                                    "面積": l_row['area'],
                                    "相場価格": l_row['market_price'],
                                    "提示価格": l_row['offer_price']
                                })
                            st.session_state.input_df = pd.DataFrame(loaded_data).astype({
                                "地権者名": "str", "面積": "float", "相場価格": "int", "提示価格": "int"
                            })
                            st.session_state.target_far = project['target_far']
                            st.session_state.exit_unit_price = project['exit_unit_price']
                            st.toast("ロードしました。シミュレーション画面へ移動してください", icon="✅")
        else:
            st.write("保存データはありません。")

if __name__ == '__main__':
    main()
