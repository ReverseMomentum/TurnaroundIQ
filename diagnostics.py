from sklearn.metrics import (
    brier_score_loss,
    log_loss,
    roc_auc_score
)


def brier_score(
    y_true,
    y_prob
):
    return brier_score_loss(
        y_true,
        y_prob
    )


def model_log_loss(
    y_true,
    y_prob
):
    return log_loss(
        y_true,
        y_prob
    )


def model_auc(
    y_true,
    y_prob
):
    return roc_auc_score(
        y_true,
        y_prob
    )


def diagnostics_report(
    y_true,
    y_prob
):

    return {
        "brier_score":
            brier_score(
                y_true,
                y_prob
            ),

        "log_loss":
            model_log_loss(
                y_true,
                y_prob
            ),

        "roc_auc":
            model_auc(
                y_true,
                y_prob
            )
    }
