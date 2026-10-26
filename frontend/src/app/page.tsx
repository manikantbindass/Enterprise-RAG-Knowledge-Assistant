import Auth from "@/components/workspace/Auth";
import Showcase from "@/components/showcase/Showcase";
export default function Page() {
  return process.env.NEXT_PUBLIC_SHOWCASE_MODE === "true" ? (
    <Showcase />
  ) : (
    <Auth />
  );
}
