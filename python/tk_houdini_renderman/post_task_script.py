import os.path

from Deadline.Scripting import *


def __main__(*args):
    deadline_plugin = args[0]

    job = deadline_plugin.GetJob()
    task = deadline_plugin.GetCurrentTask()

    output_directories = job.OutputDirectories
    output_filenames = job.OutputFileNames

    for i in range(0, len(output_directories)):
        output_directory = output_directories[i]
        output_filename = output_filenames[i]

        if not output_directory.endswith("denoise"):
            continue

        start_frame = task.GetStartFrame()
        end_frame = task.GetEndFrame()

        for frame_num in range(start_frame, end_frame + 1):
            filename = output_filename.replace("%04d", f"{frame_num:04}")
            from_path = os.path.join(
                output_directory, filename.replace("_denoise_", "_beauty_")
            )
            to_path = os.path.join(output_directory, filename)

            if os.path.exists(from_path):
                if not os.path.exists(to_path):
                    os.rename(from_path, to_path)
                    deadline_plugin.LogInfo(f"Renamed denoised frame {frame_num}")
                else:
                    deadline_plugin.LogWarning(
                        f"Renamed denoise frame {frame_num} already found: {to_path}"
                    )
            else:
                deadline_plugin.FailRender(
                    f"Can't find frame {frame_num} to denoise: {from_path}"
                )
