package com.ccb.ide.config

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage

@State(
    name = "CcbSettings",
    storages = [Storage("ccb-settings.xml")]
)
class CcbSettings : PersistentStateComponent<CcbSettings.State> {

    data class State(
        var cliPath: String = "",
        var defaultProvider: String = "claude",
        var autoInjectContext: Boolean = true,
        var showNotifications: Boolean = true
    )

    private var myState = State()

    override fun getState(): State = myState

    override fun loadState(state: State) {
        myState = state
    }

    var cliPath: String
        get() = myState.cliPath
        set(value) { myState.cliPath = value }

    var defaultProvider: String
        get() = myState.defaultProvider
        set(value) { myState.defaultProvider = value }

    var autoInjectContext: Boolean
        get() = myState.autoInjectContext
        set(value) { myState.autoInjectContext = value }

    var showNotifications: Boolean
        get() = myState.showNotifications
        set(value) { myState.showNotifications = value }

    companion object {
        fun getInstance(): CcbSettings {
            return ApplicationManager.getApplication().getService(CcbSettings::class.java)
        }
    }
}
