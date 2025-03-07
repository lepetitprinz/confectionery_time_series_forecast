import os
import sys
import datetime
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

from baseline.deployment.PipelineTimeSeries import Pipeline

path_root = os.path.join('..', '..')
# path_root = os.path.join('/', 'opt', 'DF', 'fcst')

# Data Configuration
data_cfg = {'division': 'SELL_OUT'}

# Execute Configuration
step_cfg = {
    'cls_load': True,
    'cls_cns': True,
    'cls_prep': True,
    'cls_train': True,
    'cls_pred': True,
    'cls_mdout': True
}

# Configuration
exec_cfg = {
    'cycle': True,                            # Prediction cycle

    # save configuration
    'save_step_yn': True,                     # Save each step result to object or csv
    'save_db_yn': True,                       # Save each step result to Database

    # Data preprocessing configuration
    'add_exog_dist_sales': True,
    'decompose_yn': False,                    # Decomposition
    'feature_selection_yn': False,            # Feature Selection
    'filter_threshold_cnt_yn': False,         # Filter data level under threshold count
    'filter_threshold_recent_yn': True,       # Filter data level under threshold recent week
    'filter_threshold_recent_sku_yn': True,   # Filter SKU level under threshold recent week
    'rm_fwd_zero_sales_yn': True,             # Remove forward empty sales
    'rm_outlier_yn': True,                    # Outlier clipping
    'data_imputation_yn': True,               # Data Imputation

    # Training configuration
    'scaling_yn': False,                      # Data scaling
    'grid_search_yn': False,                  # Grid Search
    'voting_yn': True                         # Add voting algorithm
}

print('------------------------------------------------')
print('Demand Forecast - SELL-OUT')
print('------------------------------------------------')
# Check start time
print("Forecast Start: ", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

pipeline = Pipeline(
    data_cfg=data_cfg,
    exec_cfg=exec_cfg,
    step_cfg=step_cfg,
    path_root=path_root
)

# Execute Baseline Forecast
pipeline.run()

# Check end time
print("Forecast End: ", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("")
