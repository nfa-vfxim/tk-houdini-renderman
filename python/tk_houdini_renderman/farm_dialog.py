# MIT License

# Copyright (c) 2021 Netherlands Film Academy

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import hou
import os
import shutil
import sys
import tempfile
from subprocess import check_output

from PySide2 import QtCore
from PySide2 import QtWidgets


class FarmSubmission(QtWidgets.QWidget):
    def __init__(
        self,
        app,
        node,
        submission_name,
        priority,
        framerange,
        network,
        parent=None,
    ):
        QtWidgets.QWidget.__init__(self, parent)
        self.setWindowTitle("Submit to Farm")
        self.app = app
        self.node = node
        self.network = network

        layout = QtWidgets.QVBoxLayout()

        self.submission_label = QtWidgets.QLabel("Submission Name")
        self.submission_name = QtWidgets.QLineEdit(submission_name)
        self.submission_name.setMinimumSize(300, 0)
        layout.addWidget(self.submission_label)
        layout.addWidget(self.submission_name)

        self.priority_label = QtWidgets.QLabel("Priority")
        self.priority = QtWidgets.QLineEdit(priority)
        layout.addWidget(self.priority_label)
        layout.addWidget(self.priority)

        self.framerange_label = QtWidgets.QLabel("Frame Range")
        self.framerange = QtWidgets.QLineEdit(framerange)
        layout.addWidget(self.framerange_label)
        layout.addWidget(self.framerange)

        self.mode_label = QtWidgets.QLabel("Mode")
        self.mode = QtWidgets.QComboBox()
        modes = ["light", "medium", "heavy"]
        self.mode.addItems(modes)
        self.mode.setCurrentIndex(2)
        layout.addWidget(self.mode_label)
        layout.addWidget(self.mode)

        buttons_layout = QtWidgets.QHBoxLayout()
        self.ok_button = QtWidgets.QPushButton("Submit")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        buttons_layout.addWidget(self.ok_button)
        buttons_layout.addWidget(self.cancel_button)

        layout.addLayout(buttons_layout)

        self.setLayout(layout)

        # Connecting buttons
        self.ok_button.clicked.connect(self.__submit_to_farm)
        self.cancel_button.clicked.connect(self.__close_window)

    def __submit_to_farm(self):
        self.close()
        submission_name = self.submission_name.text()
        priority = self.priority.text()
        framerange = self.framerange.text()

        mode = self.mode.currentIndex()
        if mode == 0:
            concurrent_tasks = "3"
        elif mode == 1:
            concurrent_tasks = "2"
        else:
            concurrent_tasks = "1"

        houdini_file = hou.hipFile.name()
        houdini_version = hou.applicationVersion()
        houdini_version = (
            str(houdini_version[0]) + "." + str(houdini_version[1])
        )

        file_parameter = "picture"
        render_filepath = self.node.parm(file_parameter).eval()

        output_directory = os.path.dirname(render_filepath)
        output_filename = os.path.basename(render_filepath)

        if self.network == "lop":
            render_rop_node = os.path.join(self.node.path(), "rop_usdrender")
            render_rop_node = render_rop_node.replace(os.sep, "/")

        else:
            render_rop_node = os.path.join(self.node.path(), "ris1")
            render_rop_node = render_rop_node.replace(os.sep, "/")

        deadline_path = os.getenv("DEADLINE_PATH")

        # Building job info properties
        job_info = [
            "Plugin=Houdini",
            "Frames=" + framerange,
            "Priority=" + priority,
            "ConcurrentTasks=" + concurrent_tasks,
            "Name=" + submission_name,
            "Department=3D",
            "OutputDirectory0=" + output_directory,
            "OutputFilename0=" + output_filename,
            "EnvironmentKeyValue0 = RENDER_ENGINE = RenderMan",
        ]

        # Building plugin info properties
        plugin_info = [
            "OutputDriver=" + render_rop_node,
            "Version=" + houdini_version,
            "SceneFile=" + houdini_file,
        ]
        # Save the file before submitting
        if hou.hipFile.hasUnsavedChanges():
            save_message = hou.ui.displayConfirmation(
                "Current file has unsaved changes, would you like to save?"
            )
            if save_message:
                hou.hipFile.save()
            else:
                hou.ui.displayMessage(
                    "Submission canceled because file is not saved.",
                    severity=hou.severityType.ImportantMessage,
                )
                return

        temporary_directory = tempfile.mkdtemp()
        self.app.logger.debug("Created temporary directory")

        try:
            # Writing job_info.txt
            job_info_filepath = os.path.join(
                temporary_directory, "job_info.txt"
            ).replace(os.sep, "/")
            job_info_textfile = open(job_info_filepath, "w")
            for item in job_info:
                job_info_textfile.write(item + "\n")
            job_info_textfile.close()

            # Writing plugin_info.txt
            plugin_info_filepath = os.path.join(
                temporary_directory, "plugin_info.txt"
            ).replace(os.sep, "/")
            plugin_info_textfile = open(plugin_info_filepath, "w")
            for item in plugin_info:
                plugin_info_textfile.write(item + "\n")
            plugin_info_textfile.close()

            deadline_command = [
                os.path.join(deadline_path, "deadlinecommand"),
                job_info_filepath,
                plugin_info_filepath,
            ]

            execute_submission = check_output(deadline_command)
            hou.ui.displayMessage("Job successfully submitted to Deadline")

        except Exception as e:
            self.app.logger.debug(
                "An error occured while submitting to farm. %s" % str(e)
            )

        finally:
            shutil.rmtree(temporary_directory)
            self.app.logger.debug("Removed temporary directory")

    def __close_window(self):
        self.app.logger.debug("Canceled submission")
        self.close()
