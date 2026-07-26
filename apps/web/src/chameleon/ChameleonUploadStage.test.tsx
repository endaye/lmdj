import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChameleonUploadStage } from "./ChameleonUploadStage";

describe("ChameleonUploadStage", () => {
  it("opens the hidden audio chooser and uploads the selected file", async () => {
    const upload = vi.fn();
    render(<ChameleonUploadStage onUpload={upload} />);
    const input = screen.getByTestId("api-file-input") as HTMLInputElement;
    const click = vi.spyOn(input, "click");

    await userEvent.click(
      screen.getByRole("button", {
        name: "Choose a WAV or MP3 to make a Patch",
      }),
    );
    expect(click).toHaveBeenCalledTimes(1);

    const file = new File(["audio"], "song.wav", { type: "audio/wav" });
    await userEvent.upload(input, file);
    expect(upload).toHaveBeenCalledWith("http://localhost:8000", file);
  });

  it("accepts one dropped WAV and shows drag-ready before drop", () => {
    const upload = vi.fn();
    render(<ChameleonUploadStage onUpload={upload} />);
    const stage = screen.getByTestId("chameleon-upload-stage");
    const file = new File(["audio"], "song.wav", { type: "audio/wav" });

    fireEvent.dragEnter(stage, { dataTransfer: { files: [file] } });
    expect(screen.getByTestId("chameleon-2d")).toHaveAttribute(
      "data-phase",
      "drag-ready",
    );
    fireEvent.drop(stage, { dataTransfer: { files: [file] } });
    expect(upload).toHaveBeenCalledWith("http://localhost:8000", file);
  });

  it("does not upload unsupported dropped files", () => {
    const upload = vi.fn();
    render(<ChameleonUploadStage onUpload={upload} />);
    fireEvent.drop(screen.getByTestId("chameleon-upload-stage"), {
      dataTransfer: {
        files: [new File(["text"], "notes.txt", { type: "text/plain" })],
      },
    });
    expect(upload).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Choose one WAV or MP3 file",
    );
  });
});
