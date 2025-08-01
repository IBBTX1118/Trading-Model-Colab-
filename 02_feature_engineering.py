# 檔名: 02_feature_engineering.py
# 版本: 3.0 (進階特徵工程版)

"""
此腳本為特徵工程的擴展版。

它會讀取處理好的市場數據，並使用 finta 函式庫，
計算出一個包含趨勢、動能、波動率、成交量等多種類別的、
龐大的技術指標特徵集，為後續的機器學習步驟做準備。

版本 3.0 新增了基於分析得出的進階複合特徵，
例如布林通道寬度、價格在通道中的位置以及成交量指標的變化率等。
"""

import logging
import sys
from pathlib import Path
from typing import List
import pandas as pd
import numpy as np # 新增 numpy 以處理可能出現的 inf
from finta import TA

# ==============================================================================
# 1. 配置區塊
# ==============================================================================
class Config:
    """儲存腳本所需的所有配置參數。"""
    INPUT_BASE_DIR = Path("Output_Data_Pipeline_v2/MarketData")
    # 更改輸出目錄，以區分舊的特徵檔案
    OUTPUT_BASE_DIR = Path("Output_Feature_Engineering/MarketData_with_Advanced_Features")
    LOG_LEVEL = "INFO"

# ==============================================================================
# 2. 特徵工程師類別
# ==============================================================================
class FeatureEngineer:
    def __init__(self, config: Config):
        self.config = config
        self.logger = self._setup_logger()
        self.config.OUTPUT_BASE_DIR.mkdir(parents=True, exist_ok=True)

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger(self.__class__.__name__)
        logger.setLevel(self.config.LOG_LEVEL.upper())
        if logger.hasHandlers():
            logger.handlers.clear()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(formatter)
        logger.addHandler(sh)
        return logger

    def find_input_files(self) -> List[Path]:
        self.logger.info(f"正在從 '{self.config.INPUT_BASE_DIR}' 尋找輸入檔案...")
        files = list(self.config.INPUT_BASE_DIR.rglob("*.parquet"))
        self.logger.info(f"找到了 {len(files)} 個 Parquet 檔案。")
        return files

    def add_features_to_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        使用 finta 為 DataFrame 添加一個龐大的特徵集，並包含進階複合特徵。
        """
        if df.empty:
            return df
        
        self.logger.info("使用 finta 計算標準及進階技術指標特徵集...")

        # --- 準備工作 ---
        df_finta = df.copy()
        df_finta.rename(columns={
            'open': 'open', 'high': 'high', 'low': 'low', 
            'close': 'close', 'tick_volume': 'volume'
        }, inplace=True)

        # --- 計算所有 finta 標準指標 ---
        
        # 趨勢指標 (Trend)
        df_finta['SMA_10'] = TA.SMA(df_finta, period=10)
        df_finta['SMA_20'] = TA.SMA(df_finta, period=20)
        df_finta['SMA_50'] = TA.SMA(df_finta, period=50)
        df_finta['EMA_10'] = TA.EMA(df_finta, period=10)
        df_finta['EMA_20'] = TA.EMA(df_finta, period=20)
        df_finta['EMA_50'] = TA.EMA(df_finta, period=50)
        df_finta = df_finta.join(TA.DMI(df_finta))
        df_finta['SAR'] = TA.SAR(df_finta)
        
        # 動能指標 (Momentum)
        df_finta['RSI_14'] = TA.RSI(df_finta, period=14)
        df_finta = df_finta.join(TA.STOCH(df_finta))
        df_finta = df_finta.join(TA.MACD(df_finta))
        df_finta['WILLIAMS'] = TA.WILLIAMS(df_finta)
        
        # 波動率指標 (Volatility)
        df_finta = df_finta.join(TA.BBANDS(df_finta))
        df_finta['ATR_14'] = TA.ATR(df_finta, period=14)
        
        # 成交量指標 (Volume)
        df_finta['OBV'] = TA.OBV(df_finta)
        df_finta['MFI'] = TA.MFI(df_finta)
        
        # 其他指標
        df_finta['CCI'] = TA.CCI(df_finta)
        
        # --- ★★★ 新增進階複合特徵 ★★★ ---
        self.logger.info("計算進階複合特徵...")

        # 1. 布林通道寬度特徵 (基於波動率)
        df_finta['BB_WIDTH'] = df_finta['BB_UPPER'] - df_finta['BB_LOWER']
        # 正規化的寬度，避免價格尺度影響
        df_finta['BB_WIDTH_RATIO'] = df_finta['BB_WIDTH'] / df_finta['SMA_20']

        # 2. 價格在布林通道中的位置特徵 (0-1之間)
        # 加上一個極小的數值避免分母為零的錯誤
        df_finta['BB_POS'] = (df_finta['close'] - df_finta['BB_LOWER']) / (df_finta['BB_WIDTH'] + 1e-9)

        # 3. 成交量指標的變化特徵 (基於成交量)
        df_finta['OBV_SMA_10'] = TA.SMA(df_finta, period=10, column='OBV')
        df_finta['OBV_PCT_CHANGE_5'] = df_finta['OBV'].pct_change(periods=5)
        
        # 4. 更多不同週期的趨勢與動能指標
        df_finta['SMA_100'] = TA.SMA(df_finta, period=100)
        df_finta['RSI_28'] = TA.RSI(df_finta, period=28)
        
        # 5. 價格與均線的關係
        df_finta['CLOSE_vs_SMA50'] = df_finta['close'] / df_finta['SMA_50']
        
        # --- 清理與收尾 ---
        
        # 將 volume 欄位名稱改回 tick_volume
        df_finta.rename(columns={'volume': 'tick_volume'}, inplace=True)
        
        # 處理計算過程中可能產生的無窮大值
        df_finta.replace([np.inf, -np.inf], np.nan, inplace=True)
        
        return df_finta

    def process_file(self, file_path: Path) -> None:
        try:
            self.logger.info(f"--- 開始處理檔案: {file_path.name} ---")
            df = pd.read_parquet(file_path)
            
            initial_cols = df.shape[1]
            df_with_features = self.add_features_to_dataframe(df)
            
            # 在儲存前丟棄所有包含 NaN 的行
            rows_before_dropna = len(df_with_features)
            df_with_features.dropna(inplace=True)
            rows_after_dropna = len(df_with_features)
            self.logger.info(f"移除了 {rows_before_dropna - rows_after_dropna} 行包含 NaN 的數據。")
            
            final_cols = df_with_features.shape[1]
            self.logger.info(f"成功添加了 {final_cols - initial_cols} 個新特徵。")
            
            # 建立與輸入對應的輸出子目錄結構
            relative_path = file_path.relative_to(self.config.INPUT_BASE_DIR)
            output_path = self.config.OUTPUT_BASE_DIR / relative_path
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            df_with_features.to_parquet(output_path)
            self.logger.info(f"已儲存帶有進階特徵的檔案到: {output_path}")

        except Exception as e:
            self.logger.error(f"處理檔案 {file_path.name} 時發生錯誤: {e}", exc_info=True)

    def run(self) -> None:
        self.logger.info("========= 進階特徵工程流程開始 (v3.0) =========")
        input_files = self.find_input_files()
        
        if not input_files:
            self.logger.warning("在輸入目錄中沒有找到任何 Parquet 檔案，流程結束。")
            return

        for file_path in input_files:
            self.process_file(file_path)
            
        self.logger.info("========= 所有檔案處理完畢，進階特徵工程流程結束 =========")

if __name__ == "__main__":
    try:
        config = Config()
        engineer = FeatureEngineer(config)
        engineer.run()
    except Exception as e:
        logging.critical(f"特徵工程腳本執行時發生未預期的嚴重錯誤: {e}", exc_info=True)
        sys.exit(1)
