<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <main class="min-h-screen bg-ly-paper pb-16 lg:pb-0">
    <div class="mx-auto max-w-3xl px-4 py-8">
      <h1 class="text-2xl font-black">立洋校园社区协议</h1>
      <p class="mt-2 text-sm text-slate-500">最后更新：2026-07-26</p>
      <div class="mt-6 space-y-4 text-sm leading-7 text-slate-700">
        <section>
          <h2 class="text-base font-bold">一、社区宗旨</h2>
          <p>立洋校园社区致力于为同学们提供友好、健康、积极的校园交流平台。请遵守法律法规与校规校纪，文明发言，尊重他人隐私。</p>
        </section>
        <section>
          <h2 class="text-base font-bold">二、用户行为规范</h2>
          <p>禁止发布以下内容：</p>
          <ul class="ml-5 list-disc">
            <li>违反宪法、法律、行政法规的内容</li>
            <li>煽动民族仇恨、歧视的内容</li>
            <li>造谣、诽谤、人身攻击</li>
            <li>色情、低俗、暴力内容</li>
            <li>商业广告、诈骗信息</li>
            <li>侵犯他人隐私、知识产权的内容</li>
          </ul>
        </section>
        <section>
          <h2 class="text-base font-bold">三、账号与安全</h2>
          <p>用户应使用真实手机号注册，妥善保管账号密码。因账号泄露造成的损失由用户自行承担。</p>
        </section>
        <section>
          <h2 class="text-base font-bold">四、违规处理</h2>
          <p>违规内容将被删除，严重违规者将被禁言或封号。管理员有权根据本协议处置违规行为。</p>
        </section>
        <section>
          <h2 class="text-base font-bold">五、免责声明</h2>
          <p>本平台不对用户发布的内容真实性负责。如发现侵权内容，请通过举报功能反馈。</p>
        </section>
      </div>
      <el-button class="mt-6" type="primary" @click="router.back()">返回</el-button>
    </div>
  </main>
</template>
