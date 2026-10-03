export async function openCreatorSystem(page) {
  if (await page.getByRole("button", {name: "Back to music", exact: true}).isVisible()) return;
  await page.getByRole("button", {name: "System", exact: true}).click();
}
export async function clickCreatorSystemAction(page, name) {
  await openCreatorSystem(page);
  await page.getByRole("button", {name, exact: true}).click();
  await page.getByRole("button", {name: "Back to music", exact: true}).click();
}
export async function openCreatorSlice(page) {
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await page.getByRole("button", {name: "Slice", exact: true}).click();
}
