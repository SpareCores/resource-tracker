from metaflow import FlowSpec, pypi_base, step, track_resources


@pypi_base(
    packages={
        "xgboost": "2.1.3",
        "scikit-learn": "1.6.1",
        "pandas": "2.2.3",
    }
)
class GbmFlow(FlowSpec):
    """Demonstrating training an XGBoost GBM model on the Covertype dataset using CPU or GPU.

    References:
    - <https://xgboost.readthedocs.io/en/stable/python/gpu-examples/cover_type.html#sphx-glr-python-gpu-examples-cover-type-py>
    """

    @track_resources
    @step
    def start(self):
        """
        Download and load the Covertype dataset.
        """
        import numpy as np
        from sklearn.datasets import fetch_covtype
        from sklearn.model_selection import train_test_split

        X, y = fetch_covtype(return_X_y=True)

        # normalize labels to start from 0 (similar to the example)
        y = y.astype(np.int32)
        y -= y.min()

        self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(
            X, y, test_size=0.25, random_state=42
        )

        self.next(self.train_model)

    @track_resources
    @step
    def train_model(self):
        """
        Train an XGBoost GBM model using GPU acceleration.
        """
        import numpy as np
        import xgboost as xgb

        try:
            # try to train a tiny model with GPU
            test_matrix = xgb.DMatrix(
                np.array([[0, 1], [2, 3]]), label=np.array([0, 1])
            )
            test_params = {"tree_method": "hist", "device": "cuda"}
            xgb.train(test_params, test_matrix, num_boost_round=1)
            print("GPU is available for XGBoost")
            gpu_available = True
        except Exception as e:
            print(f"GPU not available for XGBoost: {e}")
            gpu_available = False

        dtrain = xgb.DMatrix(self.X_train, label=self.y_train)
        dtest = xgb.DMatrix(self.X_test, label=self.y_test)
        # leave most parameters as default
        params = {
            "device": "cuda" if gpu_available else "cpu",
            "nthread": -1,
        }
        self.model = xgb.train(
            params,
            dtrain,
            num_boost_round=50,
            evals=[(dtrain, "train"), (dtest, "test")],
            early_stopping_rounds=50,
        )

        self.next(self.end)

    @step
    def end(self):
        """
        End the flow and print the results.
        """
        print(self.model.best_score)
        print("Flow completed successfully!")


if __name__ == "__main__":
    GbmFlow()
