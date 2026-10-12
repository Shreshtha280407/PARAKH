package `in`.kaushalpramaan.app.ui

import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.ui.screens.CaptureScreen
import `in`.kaushalpramaan.app.ui.screens.ConsentScreen
import `in`.kaushalpramaan.app.ui.screens.DeclarationScreen
import `in`.kaushalpramaan.app.ui.screens.EvidencePreviewScreen
import `in`.kaushalpramaan.app.ui.screens.LanguageScreen
import `in`.kaushalpramaan.app.ui.screens.LoadingScreen
import `in`.kaushalpramaan.app.ui.screens.MatchResultScreen
import `in`.kaushalpramaan.app.ui.screens.PreviewScreen
import `in`.kaushalpramaan.app.ui.screens.RegistrationScreen
import `in`.kaushalpramaan.app.ui.screens.SubmittedScreen
import `in`.kaushalpramaan.app.ui.screens.TaskDetailScreen
import `in`.kaushalpramaan.app.ui.screens.TaskListScreen
import `in`.kaushalpramaan.app.ui.screens.TrimScreen
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument

object Routes {
    const val LOADING = "loading"
    const val LANGUAGE = "language"
    const val CONSENT = "consent"
    const val REGISTRATION = "registration"
    const val DECLARATION = "declaration"
    const val MATCH_RESULT = "match_result"
    const val TASK_LIST = "task_list"
    const val TASK_DETAIL = "task_detail/{taskId}"
    const val CAPTURE = "capture/{taskId}?replaceId={replaceId}"
    const val EVIDENCE_PREVIEW = "evidence_preview/{evidenceId}"
    const val PREVIEW = "preview"
    const val SUBMITTED = "submitted"
    const val TRIM = "trim/{evidenceId}"

    fun taskDetail(taskId: String) = "task_detail/$taskId"
    fun capture(taskId: String, replaceId: String? = null) =
        "capture/$taskId" + if (replaceId != null) "?replaceId=$replaceId" else ""
    fun evidencePreview(evidenceId: String) = "evidence_preview/$evidenceId"
    fun trim(evidenceId: String) = "trim/$evidenceId"
}

@Composable
fun AppNavGraph(viewModel: AppViewModel) {
    val navController: NavHostController = rememberNavController()

    NavHost(navController = navController, startDestination = Routes.LOADING) {
        composable(Routes.LOADING) {
            val uiState by viewModel.uiState.collectAsState()
            LaunchedEffect(uiState.startRouteResolved) {
                if (uiState.startRouteResolved) {
                    val target = if (uiState.resumedFromDraft) Routes.TASK_LIST else Routes.LANGUAGE
                    navController.navigate(target) { popUpTo(Routes.LOADING) { inclusive = true } }
                }
            }
            LoadingScreen()
        }
        composable(Routes.LANGUAGE) {
            LanguageScreen(
                viewModel = viewModel,
                onContinue = { navController.navigate(Routes.CONSENT) },
            )
        }
        composable(Routes.CONSENT) {
            ConsentScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onContinue = { navController.navigate(Routes.REGISTRATION) },
            )
        }
        composable(Routes.REGISTRATION) {
            RegistrationScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onContinue = { navController.navigate(Routes.DECLARATION) },
            )
        }
        composable(Routes.DECLARATION) {
            DeclarationScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onSeeMatch = {
                    viewModel.computeMatch()
                    navController.navigate(Routes.MATCH_RESULT)
                },
            )
        }
        composable(Routes.MATCH_RESULT) {
            MatchResultScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onViewTasks = { navController.navigate(Routes.TASK_LIST) },
            )
        }
        composable(Routes.TASK_LIST) {
            TaskListScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onOpenTask = { taskId -> navController.navigate(Routes.taskDetail(taskId)) },
                onPreview = { navController.navigate(Routes.PREVIEW) },
                onDraftDeleted = {
                    navController.navigate(Routes.LANGUAGE) { popUpTo(Routes.TASK_LIST) { inclusive = true } }
                },
            )
        }
        composable(Routes.TASK_DETAIL) { backStackEntry ->
            val taskId = backStackEntry.arguments?.getString("taskId")
            requireNotNull(taskId) { "task_detail route requires a taskId argument" }
            TaskDetailScreen(
                viewModel = viewModel,
                taskId = taskId,
                onBack = { navController.popBackStack() },
                onCapture = { replaceId -> navController.navigate(Routes.capture(taskId, replaceId)) },
                onPreviewEvidence = { evidenceId -> navController.navigate(Routes.evidencePreview(evidenceId)) },
            )
        }
        composable(
            Routes.CAPTURE,
            arguments = listOf(navArgument("replaceId") { type = NavType.StringType; nullable = true }),
        ) { backStackEntry ->
            val taskId = requireNotNull(backStackEntry.arguments?.getString("taskId"))
            val replaceId = backStackEntry.arguments?.getString("replaceId")
            CaptureScreen(
                viewModel = viewModel,
                taskId = taskId,
                replacesEvidenceId = replaceId,
                onDone = { navController.popBackStack() },
            )
        }
        composable(Routes.EVIDENCE_PREVIEW) { backStackEntry ->
            val evidenceId = requireNotNull(backStackEntry.arguments?.getString("evidenceId"))
            EvidencePreviewScreen(
                viewModel = viewModel,
                evidenceId = evidenceId,
                onBack = { navController.popBackStack() },
                onRetake = { taskId, oldId ->
                    // This screen is reachable from both TaskDetail and the final review
                    // screen, so there is no single fixed ancestor to popUpTo. Pop this
                    // screen first -- capture's own onDone=popBackStack() then lands back on
                    // whichever screen actually opened it, never on this now-stale evidenceId.
                    navController.popBackStack()
                    navController.navigate(Routes.capture(taskId, oldId))
                },
                onDeleted = { navController.popBackStack() },
            )
        }
        composable(Routes.PREVIEW) {
            PreviewScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onEditTask = { taskId -> navController.navigate(Routes.taskDetail(taskId)) },
                onPreviewEvidence = { evidenceId -> navController.navigate(Routes.evidencePreview(evidenceId)) },
                onTrimEvidence = { evidenceId -> navController.navigate(Routes.trim(evidenceId)) },
                onSubmitted = {
                    navController.navigate(Routes.SUBMITTED) {
                        popUpTo(Routes.LANGUAGE) { inclusive = false }
                    }
                },
            )
        }
        composable(Routes.TRIM) { backStackEntry ->
            val evidenceId = requireNotNull(backStackEntry.arguments?.getString("evidenceId"))
            TrimScreen(
                viewModel = viewModel,
                evidenceId = evidenceId,
                onDone = { navController.popBackStack() },
                onCancel = { navController.popBackStack() },
            )
        }
        composable(Routes.SUBMITTED) {
            SubmittedScreen(
                viewModel = viewModel,
                onViewPreviewAgain = { navController.navigate(Routes.PREVIEW) },
            )
        }
    }
}
