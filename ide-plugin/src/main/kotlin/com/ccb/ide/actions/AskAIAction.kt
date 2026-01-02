package com.ccb.ide.actions

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.wm.ToolWindowManager
import com.intellij.psi.PsiFile

/**
 * Action to send selected code to AI assistant.
 *
 * Triggered via:
 * - Right-click context menu "Ask AI..."
 * - Keyboard shortcut Ctrl+Alt+A
 */
class AskAIAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val editor = e.getData(CommonDataKeys.EDITOR) ?: return
        val psiFile = e.getData(CommonDataKeys.PSI_FILE)

        // Get selected text or current line
        val selectionModel = editor.selectionModel
        val selectedText = if (selectionModel.hasSelection()) {
            selectionModel.selectedText
        } else {
            // Get current line if no selection
            val document = editor.document
            val caretOffset = editor.caretModel.offset
            val lineNumber = document.getLineNumber(caretOffset)
            val lineStart = document.getLineStartOffset(lineNumber)
            val lineEnd = document.getLineEndOffset(lineNumber)
            document.getText(com.intellij.openapi.util.TextRange(lineStart, lineEnd))
        }

        if (selectedText.isNullOrBlank()) {
            Messages.showInfoMessage(project, "Please select some code first.", "Ask AI")
            return
        }

        // Build context
        val context = buildContext(psiFile, editor, selectedText)

        // Open tool window and send message
        val toolWindow = ToolWindowManager.getInstance(project)
            .getToolWindow("Claude Code Bridge")

        if (toolWindow != null) {
            toolWindow.show {
                // Get the chat panel and send the context
                // This would need to be implemented with a proper service
                // For now, just show the tool window
            }
        }

        // Show input dialog for the question
        val question = Messages.showInputDialog(
            project,
            "What would you like to ask about this code?",
            "Ask AI",
            Messages.getQuestionIcon()
        )

        if (!question.isNullOrBlank()) {
            // Format the full prompt
            val fullPrompt = """
                |[Context]
                |File: ${psiFile?.virtualFile?.path ?: "unknown"}
                |${context}
                |
                |Code:
                |```
                |$selectedText
                |```
                |[/Context]
                |
                |$question
            """.trimMargin()

            // TODO: Send to chat panel
            // For now, copy to clipboard as a workaround
            val clipboard = java.awt.Toolkit.getDefaultToolkit().systemClipboard
            clipboard.setContents(java.awt.datatransfer.StringSelection(fullPrompt), null)

            Messages.showInfoMessage(
                project,
                "Prompt copied to clipboard. Paste it in the Claude Code Bridge panel.",
                "Ask AI"
            )
        }
    }

    override fun update(e: AnActionEvent) {
        // Only enable when editor is available
        val editor = e.getData(CommonDataKeys.EDITOR)
        e.presentation.isEnabledAndVisible = editor != null
    }

    /**
     * Build context information from PSI.
     */
    private fun buildContext(psiFile: PsiFile?, editor: com.intellij.openapi.editor.Editor, selectedText: String): String {
        if (psiFile == null) return ""

        return buildString {
            // Add line numbers
            val selectionModel = editor.selectionModel
            if (selectionModel.hasSelection()) {
                val startLine = editor.document.getLineNumber(selectionModel.selectionStart) + 1
                val endLine = editor.document.getLineNumber(selectionModel.selectionEnd) + 1
                append("Lines: $startLine-$endLine\n")
            }
        }
    }
}
