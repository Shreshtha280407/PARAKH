package `in`.kaushalpramaan.app.ui.components

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.draft.TaskDraftState
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource

@Composable
fun taskStatusText(state: TaskDraftState): String = when (state) {
    TaskDraftState.NO_EVIDENCE -> stringResource(R.string.task_status_no_evidence)
    TaskDraftState.CAPTURING -> stringResource(R.string.task_status_capturing)
    TaskDraftState.READY -> stringResource(R.string.task_status_ready)
    TaskDraftState.FAILED -> stringResource(R.string.task_status_failed)
}
