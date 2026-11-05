package com.sisa.top10

import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController

private val NetflixRed = Color(0xFFE50914)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { AppTheme { AppNav() } }
    }
}

@Composable
fun AppTheme(content: @Composable () -> Unit) {
    val scheme = if (isSystemInDarkTheme())
        darkColorScheme(primary = NetflixRed, background = Color(0xFF111111), surface = Color(0xFF1C1C1C))
    else
        lightColorScheme(primary = NetflixRed)
    MaterialTheme(colorScheme = scheme, content = content)
}

@Composable
fun AppNav() {
    val nav = rememberNavController()
    val vm: Top10ViewModel = viewModel()
    NavHost(nav, startDestination = "home") {
        composable("home") {
            HomeScreen(vm) { id -> nav.navigate("detail/${Uri.encode(id)}") }
        }
        composable("detail/{id}") { entry ->
            val id = Uri.decode(entry.arguments?.getString("id").orEmpty())
            DetailScreen(vm.title(id), onBack = { nav.popBackStack() })
        }
    }
}
