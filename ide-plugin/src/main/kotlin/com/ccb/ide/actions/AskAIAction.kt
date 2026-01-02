package com.ccb.ide.actions

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.wm.ToolWindowManager
import com.intellij.psi.PsiFile

/**
 * Action to send selected code to AI assistant in the embedded terminal.
 *
 * Triggered via:
 * - Right-click context menu "Ask AI..."
 * - Keyboard shortcut Ctrl+Alt+A
 *
 * Flow:
 * 1. Get selected code (or current line)
 * 2. Ask user for question
 * 3. Build formatted prompt with file context
 * 4. Copy to clipboard
 * 5. Open Tool Window
 * 6. Notify user to paste (Cmd+V / Ctrl+V)
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

        // Show input dialog for the question
        val question = Messages.showInputDialog(
            project,
            "What would you like to ask about this code?",
            "Ask AI",
            Messages.getQuestionIcon()
        )

        if (question.isNullOrBlank()) return

        // Build context info
        val filePath = psiFile?.virtualFile?.path ?: "unknown"
        val lineInfo = buildLineInfo(editor, selectionModel)

        // Format the prompt for Claude
        val prompt = buildPrompt(filePath, lineInfo, selectedText, question)

        // Copy to clipboard
        copyToClipboard(prompt)

        // Open tool window
        val toolWindow = ToolWindowManager.getInstance(project)
            .getToolWindow("Claude Code Bridge")

        if (toolWindow != null) {
            toolWindow.show {
                // Show notification after tool window is visible
                Messages.showInfoMessage(
                    project,
                    "Prompt copied to clipboard.\n\nPaste it in the terminal (Cmd+V / Ctrl+V).",
                    "Ask AI"
                )
            }
        } else {
            Messages.showInfoMessage(
                project,
                "Prompt copied to clipboard.\n\nOpen Claude Code Bridge and paste (Cmd+V / Ctrl+V).",
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
     * Build line number info from selection.
     */
    private fun buildLineInfo(
        editor: com.intellij.openapi.editor.Editor,
        selectionModel: com.intellij.openapi.editor.SelectionModel
    ): String {
        return if (selectionModel.hasSelection()) {
            val startLine = editor.document.getLineNumber(selectionModel.selectionStart) + 1
            val endLine = editor.document.getLineNumber(selectionModel.selectionEnd) + 1
            "Lines $startLine-$endLine"
        } else {
            val lineNumber = editor.document.getLineNumber(editor.caretModel.offset) + 1
            "Line $lineNumber"
        }
    }

    /**
     * Build the prompt to send to Claude.
     * No shell escaping needed since this goes to clipboard, not shell.
     */
    private fun buildPrompt(filePath: String, lineInfo: String, code: String, question: String): String {
        return """
            |请帮我分析以下代码：
            |
            |文件: $filePath ($lineInfo)
            |
            |```
            |$code
            |```
            |
            |问题: $question
        """.trimMargin()
    }

    /**
     * Copy text to system clipboard.
     */
    private fun copyToClipboard(text: String) {
        val clipboard = java.awt.Toolkit.getDefaultToolkit().systemClipboard
        clipboard.setContents(java.awt.datatransfer.StringSelection(text), null)
    }
}
