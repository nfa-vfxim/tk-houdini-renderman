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

import os
import shutil
import tempfile
from subprocess import check_output

import hou
from PySide2 import QtWidgets

from .get_smart_frame_list import get_smart_frame_list


class FarmSubmission(QtWidgets.QWidget):
    def __init__(
        self,
        app,
        node,
        submission_name,
        priority,
        framerange,
        render_paths,
        network,
        parent=None,
    ):
        QtWidgets.QWidget.__init__(self, parent)
        self.setWindowTitle("Submit to Farm")
        self.app = app
        self.node = node
        self.render_paths = render_paths
        self.network = network

        layout = QtWidgets.QVBoxLayout()

        self.submission_label = QtWidgets.QLabel("Submission Name")
        self.submission_name = QtWidgets.QLineEdit(submission_name)
        self.submission_name.setMinimumSize(300, 0)
        layout.addWidget(self.submission_label)
        layout.addWidget(self.submission_name)
        layout.addSpacing(8)

        self.priority_label = QtWidgets.QLabel("Priority")
        self.priority = QtWidgets.QDoubleSpinBox()
        self.priority.setDecimals(0)
        self.priority.setRange(0, 100)
        self.priority.setValue(priority)
        layout.addWidget(self.priority_label)
        layout.addWidget(self.priority)
        layout.addSpacing(8)

        self.frames_group = QtWidgets.QWidget()
        frames_group_layout = QtWidgets.QHBoxLayout()
        frames_group_layout.setContentsMargins(0, 0, 0, 0)

        self.frame_range = QtWidgets.QWidget()
        frame_range_group_layout = QtWidgets.QVBoxLayout()
        frame_range_group_layout.setContentsMargins(0, 0, 4, 0)
        self.framerange_label = QtWidgets.QLabel("Frame Range")
        self.framerange = QtWidgets.QLineEdit(framerange)
        frame_range_group_layout.addWidget(self.framerange_label)
        frame_range_group_layout.addWidget(self.framerange)
        self.frame_range.setLayout(frame_range_group_layout)
        frames_group_layout.addWidget(self.frame_range)

        self.frames_per_task = QtWidgets.QWidget()
        fpt_group_layout = QtWidgets.QVBoxLayout()
        fpt_group_layout.setContentsMargins(4, 0, 0, 0)
        self.frames_per_task_label = QtWidgets.QLabel("Frames Per Task")
        self.frames_per_task_line = QtWidgets.QDoubleSpinBox()
        self.frames_per_task_line.setDecimals(0)
        self.frames_per_task_line.setRange(0, 100)
        self.frames_per_task_line.setValue(1)
        fpt_group_layout.addWidget(self.frames_per_task_label)
        fpt_group_layout.addWidget(self.frames_per_task_line)
        self.frames_per_task.setLayout(fpt_group_layout)
        frames_group_layout.addWidget(self.frames_per_task)

        self.frames_group.setLayout(frames_group_layout)
        layout.addWidget(self.frames_group)
        layout.addSpacing(4)

        self.smartframes = QtWidgets.QCheckBox("Use Smart Frame Spreading", self)
        layout.addWidget(self.smartframes)
        layout.addSpacing(8)

        self.mode_label = QtWidgets.QLabel("Mode")
        self.mode = QtWidgets.QComboBox()
        modes = ["Light", "Medium", "Heavy"]
        self.mode.addItems(modes)
        self.mode.setCurrentIndex(2)
        layout.addWidget(self.mode_label)
        layout.addWidget(self.mode)
        layout.addSpacing(16)

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
        frames_per_task = int(self.frames_per_task_line.text())

        if frames_per_task < 1:
            hou.ui.displayMessage(
                "Submission canceled because frames per task is set below 1.",
                severity=hou.severityType.ImportantMessage,
            )
            return

        if self.smartframes.isChecked():
            framerange = get_smart_frame_list(framerange, frames_per_task)

        mode = self.mode.currentIndex()
        if mode == 0:
            concurrent_tasks = "3"
        elif mode == 1:
            concurrent_tasks = "2"
        else:
            concurrent_tasks = "1"

        houdini_file = hou.hipFile.name()
        houdini_version = hou.applicationVersion()
        houdini_version = str(houdini_version[0]) + "." + str(houdini_version[1])

        if self.network == "lop":
            render_rop_node = os.path.join(self.node.path(), "rop_usdrender")
            render_rop_node = render_rop_node.replace(os.sep, "/")

        else:
            render_rop_node = os.path.join(
                self.node.path(),
                "denoise" if self.node.evalParm("denoise") else "render",
            )
            render_rop_node = render_rop_node.replace(os.sep, "/")

        deadline_path = os.getenv("DEADLINE_PATH")

        # Building job info properties
        job_info = [
            "Plugin=Houdini",
            "Frames=" + framerange,
            "Priority=" + priority,
            "ConcurrentTasks=" + concurrent_tasks,
            "ChunkSize=" + str(frames_per_task),
            "Name=" + submission_name,
            "Department=3D",
            "EnvironmentKeyValue0 = RENDER_ENGINE = RenderMan",
            "PostTaskScript="
            + os.path.join(os.path.dirname(__file__), "post_task_script.py"),
        ]

        for i, path in enumerate(self.render_paths):
            output_directory = os.path.dirname(path)
            job_info.append("OutputDirectory{}={}".format(i, output_directory))
            if not path.endswith("denoise"):
                output_filename = os.path.basename(path).replace("$F4", "%04d")
                job_info.append("OutputFilename{}={}".format(i, output_filename))

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
