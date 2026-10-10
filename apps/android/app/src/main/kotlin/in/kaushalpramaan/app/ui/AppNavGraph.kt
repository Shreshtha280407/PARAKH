package `in`.kaushalpramaan.app.ui

import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.ui.screens.ConsentScreen
import `in`.kaushalpramaan.app.ui.screens.DeclarationScreen
import `in`.kaushalpramaan.app.ui.screens.LanguageScreen
import `in`.kaushalpramaan.app.ui.screens.MatchResultScreen
import `in`.kaushalpramaan.app.ui.screens.PreviewScreen
import `in`.kaushalpramaan.app.ui.screens.RegistrationScreen
import `in`.kaushalpramaan.app.ui.screens.SubmittedScreen
import `in`.kaushalpramaan.app.ui.screens.TaskDetailScreen
import `in`.kaushalpramaan.app.ui.screens.TaskListScreen
import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController

object Routes {
    const val LANGUAGE = "language"
    const val CONSENT = "consent"
    const val REGISTRATION = "registration"
    const val DECLARATION = "declaration"
    const val MATCH_RESULT = "match_result"
    const val TASK_LIST = "task_list"
    const val TASK_DETAIL = "task_detail/{taskId}"
    const val PREVIEW = "preview"
    const val SUBMITTED = "submitted"

    fun taskDetail(taskId: String) = "task_detail/$taskId"
}

@Composable
fun AppNavGraph(viewModel: AppViewModel) {
    val navController: NavHostController = rememberNavController()

    NavHost(navController = navController, startDestination = Routes.LANGUAGE) {
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
            )
        }
        composable(Routes.TASK_DETAIL) { backStackEntry ->
            val taskId = backStackEntry.arguments?.getString("taskId")
            requireNotNull(taskId) { "task_detail route requires a taskId argument" }
            TaskDetailScreen(
                viewModel = viewModel,
                taskId = taskId,
                onBack = { navController.popBackStack() },
            )
        }
        composable(Routes.PREVIEW) {
            PreviewScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onEditTask = { taskId -> navController.navigate(Routes.taskDetail(taskId)) },
                onSubmitted = {
                    navController.navigate(Routes.SUBMITTED) {
                        popUpTo(Routes.LANGUAGE) { inclusive = false }
                    }
                },
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
