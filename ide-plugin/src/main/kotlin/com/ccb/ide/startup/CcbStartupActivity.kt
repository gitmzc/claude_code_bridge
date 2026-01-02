package com.ccb.ide.startup

import com.ccb.ide.config.CcbSettings
import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.ProjectActivity
import com.intellij.openapi.wm.ToolWindowManager

/**
 * Optionally opens the Claude Code Bridge tool window when a project is opened.
 * Controlled by the "Auto-open on startup" setting.
 */
class CcbStartupActivity : ProjectActivity {

    override suspend fun execute(project: Project) {
        // Check if auto-open is enabled in settings
        val settings = CcbSettings.getInstance()
        if (!settings.autoOpenOnStartup) {
            return
        }

        // Open tool window after project is fully loaded
        val toolWindowManager = ToolWindowManager.getInstance(project)
        val toolWindow = toolWindowManager.getToolWindow("Claude Code Bridge")
        toolWindow?.show()
    }
}
