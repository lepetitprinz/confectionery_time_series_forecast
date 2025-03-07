import common.util as util
import common.config as config
from dao.DataIO import DataIO
from common.SqlConfig import SqlConfig

import os
from typing import Dict, Tuple
import datetime
import numpy as np
import pandas as pd

import matplotlib.pyplot as plt
# import matplotlib.font_manager as fm
# font_path = r'C:\Windows\Fonts\malgun.ttf'
# font_name = fm.FontProperties(fname=font_path).get_name()
# matplotlib.rc('font', family='Malgun Gothic')
plt.style.use('fivethirtyeight')


class CalcAccuracy(object):
    col_fixed = ['division_cd', 'start_week_day', 'week']
    pick_sp1 = {
        # SP1: 도봉 / 안양 / 동울산 / 논산 / 동작 / 진주 / 이마트 / 롯데슈퍼 / 7-11
        'P1': ['1005', '1022', '1051', '1063', '1107', '1128', '1065', '1073', '1173', '1196'],
        'P2': ['1017', '1098', '1101', '1112', '1128', '1206', '1213', '1230']
    }
    pred_csv_map = {
        'name': {
            'C1-P3': 'pred_best.csv',
            'C1-P5': 'pred_middle_out_db.csv'
        },
        'encoding': {
            'C1-P3': 'cp949',
            'C1-P5': 'utf-8'
        }
    }

    def __init__(self, exec_kind: str, step_cfg: dict, exec_cfg: dict, date_cfg: dict, data_cfg: dict):
        # Object instance attribute
        self.io = DataIO()
        self.sql_conf = SqlConfig()
        self.root_path = data_cfg['root_path']
        self.save_path = data_cfg['save_path']
        self.common = self.io.get_dict_from_db(
            sql=SqlConfig.sql_comm_master(),
            key='OPTION_CD',
            val='OPTION_VAL'
        )
        # Execution instance attribute
        self.exec_kind = exec_kind
        self.step_cfg = step_cfg
        self.exec_cfg = exec_cfg
        self.date_cfg = date_cfg
        self.data_cfg = data_cfg

        # Data instance attribute
        self.level = {}
        self.hrchy = {}
        self.division = data_cfg['division']
        self.cust_map = {}
        self.item_info = None
        self.date_sales = {}
        self.data_vrsn_cd = ''
        self.hist_date_range = []

        # Evaluation instance attribute
        self.week_compare = 1             # Compare week range
        self.sales_threshold = 5          # Minimum sales quantity
        self.eval_threshold = 0.5         # Accuracy: Success or not
        self.filter_acc_rate = 2          # Filter accuracy rate
        self.filter_top_n_threshold = 1   # Filter top N
        self.filter_sales_threshold_standard = 'recent'    # hist / recent

    def run(self) -> None:
        # Initialize information
        self.init()

        # Load the dataset
        sales_compare, sales_hist, pred = self.load_dataset()

        # Preprocess the dataset
        if self.step_cfg['cls_prep']:
            sales_hist, sales_compare = self.preprocessing(sales_hist=sales_hist, sales_compare=sales_compare)

        # Compare result
        result = None
        if self.step_cfg['cls_comp']:
            result = self.compare_result(sales=sales_compare, pred=pred)

        # Change data type (string to datetime)
        sales_hist = self.conv_to_datetime(data=sales_hist, col='start_week_day')
        result = self.conv_to_datetime(data=result, col='start_week_day')

        if self.exec_cfg['pick_specific_biz_yn']:
            result = result[result['item_attr01_cd'] == self.data_cfg['item_attr01_cd']]

        # Accuracy rate bu SP1 + item level
        # if self.exec_cfg['calc_acc_by_sp1_item_yn']:
        #     self.calc_acc_by_sp1_line(data=result, sp1_list=self.pick_sp1[self.data_cfg['item_attr01_cd']])

        # Execute on top N accuracy
        if self.step_cfg['cls_top_n']:
            # Execute on specific sp1 list
            if self.exec_cfg['pick_specific_sp1_yn']:
                result_pick = self.pick_specific_sp1(data=result)
                for sp1, data in result_pick.items():
                    # Filter n by accuracy
                    data_filter_n = self.filter_n_by_accuracy(data=data)

                    # Draw plots
                    if self.step_cfg['cls_graph']:
                        self.draw_plot(result=data_filter_n, sales=sales_hist)

            else:
                # Filter n by accuracy
                result = self.filter_n_by_accuracy(data=result)

                # Draw plots
                if self.step_cfg['cls_graph']:
                    self.draw_plot(result=result, sales=sales_hist)

    # def calc_acc_by_sp1_line(self, data: pd.DataFrame, sp1_list=None) -> None:
    #     if sp1_list is not None:
    #         data = data[data['cust_grp_cd'].isin(sp1_list)]
    #
    #     grp_col = ['cust_grp_cd', 'item_attr01_cd', 'item_attr02_cd']
    #     grp_avg = data.groupby(by=grp_col)['success'].mean().reset_index()
    #     grp_avg_pivot = grp_avg.pivot(
    #         index=['item_attr01_cd', 'item_attr02_cd'],
    #         columns='cust_grp_cd',
    #         values='success')
    #
    #     path = os.path.join(self.save_path, self.data_vrsn_cd,
    #                         self.data_vrsn_cd + '_' + self.division + '_' + str(self.hrchy['lvl']['item']) +
    #                         '_' + self.data_cfg['item_attr01_cd'] + '_pivot.csv')
    #
    #     grp_avg_pivot.to_csv(path)

    def preprocessing(self, sales_hist: pd.DataFrame, sales_compare: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        # Resample data
        sales_compare = self.resample_sales(data=sales_compare)
        sales_hist = self.resample_sales(data=sales_hist)

        # remove zero quantity
        if self.exec_cfg['rm_zero_yn']:
            print("Remove zero sales quantities")
            sales_compare = self.filter_zeros(data=sales_compare, col='sales')

        if self.exec_cfg['filter_sales_threshold_yn']:
            print(f"Filter sales under {self.sales_threshold} quantity")
            sales_compare = self.filter_sales_threshold(hist=sales_hist, recent=sales_compare)

        return sales_hist, sales_compare

    def pick_specific_sp1(self, data: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        pick_sp1 = self.pick_sp1[self.data_cfg['item_attr01_cd']]
        data_pick = data[data['cust_grp_cd'].isin(pick_sp1)]

        # sorting
        data_pick = data_pick.sort_values(by=['cust_grp_cd', 'accuracy'])

        # split by sp1
        split = {}
        for sp1 in pick_sp1:
            temp = data_pick[data_pick['cust_grp_cd'] == sp1]
            if len(temp) > 0:
                split[sp1] = temp.reset_index(drop=True)

        return split

    def filter_sales_threshold(self, hist: pd.DataFrame, recent: pd.DataFrame) -> pd.DataFrame:
        recent_filtered = None
        if self.filter_sales_threshold_standard == 'hist':
            hist_avg = self.calc_avg_sales(data=hist)
            hist_data_level = self.filter_avg_sales_by_threshold(data=hist_avg)
            recent_filtered = self.merged_filtered_data_level(data=recent, data_level=hist_data_level)

        elif self.filter_sales_threshold_standard == 'recent':
            recent_filtered = recent[recent['sales'] >= self.sales_threshold]

        return recent_filtered

    def calc_avg_sales(self, data: pd.DataFrame) -> pd.DataFrame:
        avg = data.groupby(by=self.hrchy['apply']).mean()
        avg = avg.reset_index()

        return avg

    def filter_avg_sales_by_threshold(self, data: pd.DataFrame) -> pd.DataFrame:
        data = data[data['sales'] >= self.sales_threshold]
        data = data[self.hrchy['apply']]    # Data level columns

        return data

    def merged_filtered_data_level(self, data: pd.DataFrame, data_level: pd.DataFrame) -> pd.DataFrame:
        merged = pd.merge(data, data_level, on=self.hrchy['apply'], how='inner')

        return merged

    def init(self) -> None:
        self.set_date()         # Set date
        self.set_level(item_lvl=self.data_cfg['item_lvl'])
        self.set_hrchy()        # Set the hierarchy
        self.get_item_info()    # Get item information
        self.get_cust_info()    # Get customer information
        self.make_dir()         # Make the directory

    def get_cust_info(self) -> None:
        cust_info = self.io.get_df_from_db(sql=self.sql_conf.sql_cust_grp_info())
        cust_info['cust_grp_cd'] = cust_info['cust_grp_cd'].astype(str)
        cust_info = cust_info.set_index('cust_grp_cd')['cust_grp_nm'].to_dict()

        self.cust_map = cust_info

    def get_item_info(self) -> None:
        item_info = self.io.get_df_from_db(sql=self.sql_conf.sql_item_view())
        item_info.columns = [config.HRCHY_CD_TO_DB_CD_MAP.get(col, col) for col in item_info.columns]
        item_info.columns = [config.HRCHY_SKU_TO_DB_SKU_MAP.get(col, col) for col in item_info.columns]

        if 'item_cd' in item_info.columns:
            item_info['item_cd'] = item_info['item_cd'].astype(str)

        item_col_grp = self.hrchy['list']['item']
        item_col_grp = [[col, col[:-2] + 'nm'] for col in item_col_grp]
        item_col_list = []
        for col in item_col_grp:
            item_col_list.extend(col)

        item_info = item_info[item_col_list].drop_duplicates()
        # item_lvl_cd = self.hrchy['apply'][-1]
        # item_lvl_nm = item_lvl_cd[:-2] + 'nm'
        # item_info = item_info[[item_lvl_cd, item_lvl_nm]].drop_duplicates()
        # item_code_map = item_info.set_index(item_lvl_cd)[item_lvl_nm].to_dict()

        self.item_info = item_info

    def set_date(self) -> None:
        if self.date_cfg['cycle_yn']:
            self.date_sales = self.date_cfg['date']
            # self.date_sales = self.calc_sales_date()
            self.data_vrsn_cd = self.date_sales['hist']['from'] + '-' + self.date_sales['hist']['to']
            self.hist_date_range = pd.date_range(
                start=self.date_sales['hist']['from'],
                end=self.date_sales['hist']['to'],
                freq='w'
            )
        else:
            self.date_sales = self.date_cfg['date']
            self.data_vrsn_cd = self.date_cfg['data_vrsn_cd']
            self.hist_date_range = pd.date_range(
                start=self.date_sales['hist']['from'],
                end=self.date_sales['hist']['to'],
                freq='W-MON'
            )

    def set_level(self,  item_lvl: int) -> None:
        level = {
            'cust_lvl': 1,    # Fixed
            'item_lvl': item_lvl,
        }
        self.level = level

    def set_hrchy(self) -> None:
        self.hrchy = {
            'cnt': 0,
            'key': "C" + str(self.level['cust_lvl']) + '-' + "P" + str(self.level['item_lvl']) + '-',
            'lvl': {
                'cust': self.level['cust_lvl'],
                'item': self.level['item_lvl'],
                'total': self.level['cust_lvl'] + self.level['item_lvl']
            },
            'list': {
                'cust': self.common['hrchy_cust'].split(','),
                'item': [config.HRCHY_CD_TO_DB_CD_MAP.get(col, 'item_cd') for col
                         in self.common['hrchy_item'].split(',')[:self.level['item_lvl']]]
            }
        }
        self.hrchy['apply'] = self.hrchy['list']['cust'] + self.hrchy['list']['item']

    def make_dir(self) -> None:
        path = os.path.join(self.save_path, self.data_vrsn_cd)
        if not os.path.isdir(path):
            os.mkdir(path=path)
            if self.step_cfg['cls_graph']:
                os.mkdir(path=os.path.join(path, 'plot'))

    def calc_sales_date(self) -> Dict[str, Dict[str, str]]:
        today = datetime.date.today()
        today = today - datetime.timedelta(days=today.weekday())

        # History dates
        hist_from = today - datetime.timedelta(days=int(self.common['week_hist']) * 7 + 7)
        hist_to = today - datetime.timedelta(days=1 + 7)

        hist_from = hist_from.strftime('%Y%m%d')
        hist_to = hist_to.strftime('%Y%m%d')

        # Compare dates
        compare_from = today - datetime.timedelta(days=self.week_compare * 7)
        compare_to = today - datetime.timedelta(days=1)

        compare_from = compare_from.strftime('%Y%m%d')
        compare_to = compare_to.strftime('%Y%m%d')

        date = {
            'hist': {
                'from': hist_from,
                'to': hist_to
            },
            'compare': {
                'from': compare_from,
                'to': compare_to
            }
        }

        return date

    def load_dataset(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        # load sales dataset
        info_sales_compare = {
            'division_cd': self.division,
            'start_week_day': self.date_sales['compare']['from']
        }
        sales_compare = None
        if self.division == 'SELL_IN':  # Sell-In Dataset
            sales_compare = self.io.get_df_from_db(sql=self.sql_conf.sql_sell_week_compare(**info_sales_compare))
        elif self.division == 'SELL_OUT':  # Sell-Out Dataset
            sales_compare = self.io.get_df_from_db(sql=self.sql_conf.sql_sell_week_compare(**info_sales_compare))

        info_sales_hist = {
            'division_cd': self.division,
            'from': self.date_sales['hist']['from'],
            'to': self.date_sales['hist']['to']
        }
        sales_hist = None
        if self.division == 'SELL_IN':  # Sell-In Dataset
            sales_hist = self.io.get_df_from_db(sql=self.sql_conf.sql_sell_week_hist(**info_sales_hist))
        elif self.division == 'SELL_OUT':  # Sell-Out Dataset
            sales_hist = self.io.get_df_from_db(sql=self.sql_conf.sql_sell_week_hist(**info_sales_hist))

        # load prediction dataset
        pred = None
        if self.data_cfg['load_option'] == 'db':
            info_pred = {
                'data_vrsn_cd': self.data_vrsn_cd,
                'division_cd': self.division,
                'fkey': self.hrchy['key'][:-1],
                'yymmdd': self.date_sales['compare']['from'],
            }
            pred = self.io.get_df_from_db(sql=self.sql_conf.sql_pred_best(**info_pred))

        elif self.data_cfg['load_option'] == 'csv':
            path = os.path.join(self.root_path, 'prediction', self.exec_kind, self.data_vrsn_cd,
                                self.division + '_' + self.data_vrsn_cd + '_C1-P3-'
                                + self.pred_csv_map['name'][self.hrchy['key'][:-1]])
            pred = pd.read_csv(path, encoding=self.pred_csv_map['encoding'][self.hrchy['key'][:-1]])
            pred.columns = [col.lower() for col in pred.columns]
            pred = pred.rename(columns={'yymmdd': 'start_week_day', 'result_sales': 'pred'})
            pred['cust_grp_cd'] = pred['cust_grp_cd'].astype(str)
            pred['start_week_day'] = pred['start_week_day'].astype(str)
            if 'item_cd' in pred.columns:
                pred['item_cd'] = pred['item_cd'].astype(str)

        pred = self.filter_col(data=pred)

        return sales_compare, sales_hist, pred

    def filter_col(self, data: pd.DataFrame) -> pd.DataFrame:
        filter_col = self.hrchy['apply'] + self.col_fixed + ['pred']
        data = data[filter_col]

        return data

    def resample_sales(self, data: pd.DataFrame) -> pd.DataFrame:
        grp_col = self.hrchy['apply'] + self.col_fixed
        data = data.groupby(by=grp_col).sum()
        data = data.reset_index()

        return data

    @staticmethod
    def filter_zeros(data: pd.DataFrame, col: str) -> pd.DataFrame:
        return data[data[col] != 0]

    def fill_missing_date(self, df: pd.DataFrame, col: str) -> pd.DataFrame:
        idx_add = list(set(self.hist_date_range) - set(df[col]))
        data_add = np.zeros(len(idx_add))
        # df_add = pd.DataFrame(data_add, index=idx_add, columns=df.columns)
        df_add = pd.DataFrame(np.array([idx_add, data_add]).T, columns=df.columns)
        df = df.append(df_add)
        df = df.sort_values(by=col)

        return df

    def merge_result(self, sales: pd.DataFrame, pred: pd.DataFrame) -> pd.DataFrame:
        merge_col = self.hrchy['apply'] + self.col_fixed
        merged = pd.merge(
            pred,
            sales,
            on=merge_col,
            how='inner'    # Todo: choose left or inner
        )
        merged['pred'] = merged['pred'].fillna(0)
        merged['sales'] = merged['sales'].fillna(0)

        return merged

    def compare_result(self, sales: pd.DataFrame, pred: pd.DataFrame) -> pd.DataFrame:
        # Merge dataset
        data = self.merge_result(sales=sales, pred=pred)

        # Calculate the accuracy
        data = self.calc_accuracy(data=data)
        data = self.eval_result(data=data)

        # Add name information
        # Add SP1 name
        data['cust_grp_nm'] = [self.cust_map.get(code, code) for code in data['cust_grp_cd'].values]

        # Add item names
        data = pd.merge(data, self.item_info, how='left', on=self.hrchy['list']['item'])

        view_col = ['cust_grp_cd', 'cust_grp_nm'] + list(self.item_info.columns) + ['sales', 'pred', 'accuracy']
        data_save = data[view_col]

        # Save the result
        path = os.path.join(self.save_path, self.data_vrsn_cd, self.data_vrsn_cd + '_' + self.division +
                            '_' + str(self.hrchy['lvl']['item']) + '.csv')
        data_save.to_csv(path, index=False, encoding='cp949')

        return data

    @staticmethod
    def calc_accuracy(data) -> pd.DataFrame:
        conditions = [
            data['sales'] == data['pred'],
            data['sales'] == 0,
            data['sales'] != data['pred']
        ]
        # values = [1, 0, data['pred'] / data['sales']]
        values = [1, 0, data['sales'] / data['pred']]    # Todo: Change logic (22.02.09)
        data['accuracy'] = np.select(conditions, values)

        # customize accuracy
        data = util.customize_accuracy(data=data, col='accuracy')
        # accuracy = np.where(accuracy > 1, 2 - accuracy, accuracy)
        # accuracy = np.where(accuracy < 0, 0, accuracy)
        #
        # data['accuracy'] = accuracy

        return data

    def eval_result(self, data) -> pd.DataFrame:
        data['success'] = np.where(data['accuracy'] < self.eval_threshold, 0, 1)
        # data['success'] = np.where(data['accuracy'] < self.eval_threshold, 'N', 'Y')

        len_total = len(data)
        len_success = len(data[data['success'] == 1])
        len_fail = len(data[data['success'] == 0])

        print("---------------------------------")
        print(f"Prediction Total: {len_total}")
        print(f"Prediction Success: {len_success}, {round(len_success/len_total, 3)}")
        print(f"Prediction Fail: {len_fail}, {round(len_fail/len_total, 3)}")
        print("---------------------------------")

        return data

    def filter_n_by_accuracy(self, data) -> Dict[str, pd.DataFrame]:
        data = data.sort_values(by=['accuracy'], ascending=False)
        data = data[data['accuracy'] != 1]    # remove zero equal zero case
        best = data.iloc[:self.filter_top_n_threshold, :]
        worst = data.iloc[-self.filter_top_n_threshold:, :]
        worst = worst.fillna(0)

        result = {'best': best, 'worst': worst}

        return result

    def draw_plot(self, result: dict, sales: pd.DataFrame):
        item_lvl_col = self.hrchy['list']['item'][-1]
        plt.clf()
        for kind, data in result.items():
            for cust_grp, item_lvl_cd, date, pred, sale in zip(
                    data['cust_grp_cd'], data[item_lvl_col], data['start_week_day'], data['pred'], data['sales']
            ):

                filtered = sales[(sales['cust_grp_cd'] == cust_grp) & (sales[item_lvl_col] == item_lvl_cd)]
                filtered = filtered[['start_week_day', 'sales']]
                filtered = self.fill_missing_date(df=filtered, col='start_week_day')

                fig, ax1 = plt.subplots(1, 1, figsize=(15, 6))
                # fig, ax1 = plt.subplots(1, 1, figsize=(6, 6))
                ax1.plot(filtered['start_week_day'], filtered['sales'],
                         linewidth=1.3, color='grey', label='history')

                if len(filtered) > 0:
                    df_sales = self.connect_dot(hist=filtered, date=date, value=sale)
                    df_pred = self.connect_dot(hist=filtered, date=date, value=pred)
                    ax1.plot(df_sales['start_week_day'], df_sales['qty'], color='darkblue',
                             linewidth=1.3, alpha=0.7)
                    ax1.plot(df_pred['start_week_day'], df_pred['qty'], color='firebrick',
                             linewidth=2, alpha=0.8, linestyle='dotted')

                    # Ticks
                    # plt.xlim(xmin=df_sales['start_week_day'].tolist()[0],
                    #          xmax=df_sales['start_week_day'].tolist()[-1])
                    plt.xticks(rotation=30)
                    plt.ylim(ymin=-5)
                    date_str = datetime.datetime.strftime(date, '%Y%m%d')
                    plt.title(f'Date: {date_str} / Cust Group: {cust_grp} / Brand: {self.item_info.get(item_lvl_cd, item_lvl_cd)}')
                    plt.tight_layout()
                    plt.savefig(os.path.join(
                        self.root_path, 'analysis', 'accuracy',
                        self.data_vrsn_cd, 'plot', self.data_vrsn_cd + '_' + self.division + '_' +
                        kind + '_' + str(cust_grp) + '_' + str(item_lvl_cd) + '.png'))

                    plt.close(fig)

    @staticmethod
    def connect_dot(hist: pd.DataFrame, date, value) -> pd.DataFrame:
        hist = hist[['start_week_day', 'sales']]
        hist = hist.rename(columns={'sales': 'qty'})
        hist = hist.sort_values(by='start_week_day')

        result = pd.DataFrame({'start_week_day': [date], 'qty': [value]})
        result = result.append(hist.iloc[-1, :], ignore_index=True)

        return result

    @staticmethod
    def conv_to_datetime(data: pd.DataFrame, col: str) -> pd.DataFrame:
        data[col] = pd.to_datetime(data[col])

        return data
